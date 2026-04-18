"""Message handler: orchestrates validate → verify signature → persist → DLQ.

Ed25519 verification is optional at this layer: tests can opt out, and dev
stacks can run with `REQUIRE_SIGNATURE=false` to ease bootstrap. In
production the verifier is injected and enforcement is mandatory.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from .persister import Executor, persist_dead_letter, persist_payloads
from .validator import validate


log = logging.getLogger(__name__)


# A verifier is a callable: payload -> bool. Returning True means the
# signature is valid (or verification is intentionally skipped, e.g. tests).
Verifier = Callable[[dict[str, Any]], bool]


def always_true_verifier(_payload: dict[str, Any]) -> bool:
    return True


@dataclass
class HandleResult:
    ok: bool
    rows_inserted: int
    reason: str | None = None


def handle_message(
    executor: Executor,
    topic: str,
    raw_payload: bytes | str,
    dead_letter_enabled: bool = True,
    verifier: Verifier | None = None,
) -> HandleResult:
    """Process one MQTT message end-to-end.

    Pipeline:
      1. Parse JSON
      2. JSON Schema validate
      3. Topic↔payload identity match (anti-spoofing)
      4. Ed25519 signature verify (if verifier provided)
      5. Persist with ON CONFLICT DO NOTHING (idempotent)
      On any failure, write to dead_letter with a reason tag.
    """
    text = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        return _dead_letter(
            executor, topic, text, "json_parse_error", str(e), dead_letter_enabled
        )

    ok, errors = validate(payload)
    if not ok:
        return _dead_letter(
            executor, topic, text, "schema_validation", "; ".join(errors),
            dead_letter_enabled,
        )

    mismatch = _topic_vs_payload_mismatch(topic, payload)
    if mismatch:
        return _dead_letter(
            executor, topic, text, "topic_payload_mismatch", mismatch,
            dead_letter_enabled,
        )

    if verifier is not None:
        try:
            valid = verifier(payload)
        except Exception as e:
            log.exception("verifier raised for topic=%s", topic)
            return _dead_letter(
                executor, topic, text, "signature_error", str(e),
                dead_letter_enabled,
            )
        if not valid:
            return _dead_letter(
                executor, topic, text, "signature_invalid",
                "Ed25519 verify failed or unknown device",
                dead_letter_enabled,
            )

    try:
        inserted = persist_payloads(executor, [payload])
        return HandleResult(ok=True, rows_inserted=inserted)
    except Exception as e:
        log.exception("persist failed for topic %s", topic)
        return _dead_letter(
            executor, topic, text, "persist_error", str(e), dead_letter_enabled
        )


def _dead_letter(
    executor: Executor,
    topic: str,
    text: str,
    reason: str,
    details: str,
    enabled: bool,
) -> HandleResult:
    if enabled:
        try:
            persist_dead_letter(executor, topic, text, reason, details)
        except Exception:
            log.exception("failed to write to dead_letter (reason=%s)", reason)
    return HandleResult(ok=False, rows_inserted=0, reason=reason)


def _topic_vs_payload_mismatch(topic: str, payload: dict[str, Any]) -> str | None:
    parts = topic.split("/")
    if len(parts) != 6 or parts[0] != "tel":
        return f"unexpected topic shape: {topic!r}"

    _, site, gw, dev, sensor, _leaf = parts
    expected = {
        "site": payload.get("site"),
        "gateway": payload.get("gateway"),
        "device": payload.get("device"),
        "sensor": payload.get("sensor"),
    }
    actual = {"site": site, "gateway": gw, "device": dev, "sensor": sensor}
    if expected != actual:
        return f"payload ids {expected} != topic ids {actual}"
    return None
