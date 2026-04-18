"""Message handler: orchestrates validate → persist → dead-letter.

Pure function on top of injected executor. No MQTT or driver knowledge here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .persister import Executor, persist_dead_letter, persist_payloads
from .validator import validate


log = logging.getLogger(__name__)


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
) -> HandleResult:
    """Process one MQTT message end-to-end.

    - Parse JSON
    - Validate against schema
    - Check that topic path matches payload identifiers (defense-in-depth)
    - Insert with ON CONFLICT DO NOTHING (idempotent)
    - On any failure, write to dead_letter if enabled
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

    try:
        inserted = persist_payloads(executor, [payload])
        return HandleResult(ok=True, rows_inserted=inserted)
    except Exception as e:  # DB errors — DLQ and keep the pipeline alive.
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
    """Ensures topic segments match identifiers in the payload.

    Prevents a compromised device from publishing on another site's topic.
    Expected topic shape:  tel/<site>/<gw>/<dev>/<sensor>/<leaf>
    """
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
