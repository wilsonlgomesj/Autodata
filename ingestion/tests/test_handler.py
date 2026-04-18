"""End-to-end handler tests with a fake executor.

Covers: valid ingestion, JSON parse error, schema failure, topic/payload
mismatch, and DB persistence failure.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingestion.handler import handle_message  # type: ignore

from .fakes import FakeExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAYLOAD_DIR = REPO_ROOT / "examples" / "payloads"


def _load_text(name: str) -> str:
    return (PAYLOAD_DIR / name).read_text()


def _topic_for(payload: dict, leaf: str = "meas") -> str:
    return (
        f"tel/{payload['site']}/{payload['gateway']}/"
        f"{payload['device']}/{payload['sensor']}/{leaf}"
    )


def test_valid_message_persists_and_returns_ok():
    raw = _load_text("piezometer_vw_good.json")
    payload = json.loads(raw)
    topic = _topic_for(payload)

    executor = FakeExecutor()
    result = handle_message(executor, topic, raw)

    assert result.ok is True
    assert result.rows_inserted == 3
    assert executor.sql_contains("INSERT INTO geo.measurement")
    assert not executor.sql_contains("dead_letter")


def test_invalid_json_goes_to_dead_letter():
    executor = FakeExecutor()
    result = handle_message(
        executor, "tel/a/b/c/d/meas", b"{this is not json"
    )
    assert result.ok is False
    assert result.reason == "json_parse_error"
    assert executor.sql_contains("dead_letter")


def test_schema_violation_goes_to_dead_letter():
    bad = {
        "schema": "geo.telemetry.v1",
        # missing almost every required field
    }
    executor = FakeExecutor()
    result = handle_message(
        executor, "tel/a/b/c/d/meas", json.dumps(bad)
    )
    assert result.ok is False
    assert result.reason == "schema_validation"
    assert executor.sql_contains("dead_letter")


def test_topic_mismatch_goes_to_dead_letter():
    raw = _load_text("piezometer_vw_good.json")
    payload = json.loads(raw)
    # Fake topic with wrong site to simulate spoofing attempt
    topic = f"tel/other-site/{payload['gateway']}/{payload['device']}/{payload['sensor']}/meas"

    executor = FakeExecutor()
    result = handle_message(executor, topic, raw)

    assert result.ok is False
    assert result.reason == "topic_payload_mismatch"
    assert executor.sql_contains("dead_letter")


def test_persist_failure_goes_to_dead_letter():
    raw = _load_text("piezometer_vw_good.json")
    payload = json.loads(raw)
    topic = _topic_for(payload)

    executor = FakeExecutor(raise_on_sql_substring="INSERT INTO geo.measurement")
    result = handle_message(executor, topic, raw)

    assert result.ok is False
    assert result.reason == "persist_error"
    # dead letter should have been attempted (a different SQL substring)
    assert executor.sql_contains("dead_letter")


def test_dead_letter_disabled_still_returns_failure_reason():
    executor = FakeExecutor()
    result = handle_message(
        executor, "tel/a/b/c/d/meas", b"not json",
        dead_letter_enabled=False,
    )
    assert result.ok is False
    assert result.reason == "json_parse_error"
    assert not executor.sql_contains("dead_letter")


def test_unexpected_topic_shape_rejected():
    raw = _load_text("piezometer_vw_good.json")
    executor = FakeExecutor()
    # Topic missing the leaf segment
    result = handle_message(executor, "tel/a/b/c/d", raw)
    assert result.ok is False
    assert result.reason == "topic_payload_mismatch"
