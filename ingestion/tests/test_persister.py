"""Unit tests for persister.fanout_payload_to_rows and persist_payloads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.persister import (  # type: ignore
    fanout_payload_to_rows,
    persist_payloads,
    MEASUREMENT_INSERT_SQL,
)

from .fakes import FakeExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAYLOAD_DIR = REPO_ROOT / "examples" / "payloads"


def _load(name: str) -> dict:
    return json.loads((PAYLOAD_DIR / name).read_text())


def test_fanout_scalar_values_produces_one_row_per_metric():
    payload = _load("piezometer_vw_good.json")
    rows = fanout_payload_to_rows(payload)

    # piezometer_vw has 3 metrics: pressure_kpa, frequency_hz, temp_c
    assert len(rows) == 3
    metrics = {r.metric for r in rows}
    assert metrics == {"pressure_kpa", "frequency_hz", "temp_c"}

    # All rows share identifiers
    for r in rows:
        assert r.site_id == payload["site"]
        assert r.sensor_id == payload["sensor"]
        assert r.msg_id == payload["msg_id"]
        assert r.quality == "GOOD"
        assert r.value is not None
        assert r.value_array is None


def test_fanout_preserves_quality_flags():
    payload = _load("piezometer_vw_suspect.json")
    rows = fanout_payload_to_rows(payload)
    assert all(r.quality == "SUSPECT" for r in rows)
    assert all(set(r.flags) == {"STEP", "CROSS_SENSOR"} for r in rows)


def test_persist_calls_executor_with_idempotent_sql():
    payload = _load("inclinometer_ipi_mems.json")
    executor = FakeExecutor()
    inserted = persist_payloads(executor, [payload])

    assert inserted == 3  # tilt_x_deg, tilt_y_deg, temp_c
    assert len(executor.calls) == 1
    assert "ON CONFLICT" in executor.calls[0].sql
    assert "DO NOTHING" in executor.calls[0].sql
    # Ensure the uniqueness columns appear in the conflict target
    assert "(site_id, sensor_id, metric, msg_id)" in executor.calls[0].sql


def test_persist_multiple_payloads_batches_into_single_call():
    payloads = [
        _load("piezometer_vw_good.json"),
        _load("rain_gauge_event.json"),
    ]
    executor = FakeExecutor()
    inserted = persist_payloads(executor, payloads)
    # 3 metrics from PZ + 2 from rain = 5
    assert inserted == 5
    assert len(executor.calls) == 1
    rows = executor.calls[0].rows
    assert len(rows) == 5


def test_fanout_rejects_non_numeric_values():
    bad = {
        "site": "x", "sensor": "y", "t_sample": "2026-01-01T00:00:00.000Z",
        "msg_id": "0" * 26, "seq": 1,
        "quality": {"code": "GOOD"},
        "values": {"weird": "string_not_number"},
    }
    with pytest.raises(ValueError):
        fanout_payload_to_rows(bad)


def test_fanout_handles_array_values():
    # Simulated fiber DTS-style payload
    payload = {
        "site": "s", "sensor": "dts-01", "t_sample": "2026-01-01T00:00:00.000Z",
        "msg_id": "0" * 26, "seq": 1,
        "quality": {"code": "GOOD"},
        "values": {"temperature_c": [22.1, 22.3, 22.5]},
    }
    rows = fanout_payload_to_rows(payload)
    assert len(rows) == 1
    assert rows[0].value is None
    assert rows[0].value_array == [22.1, 22.3, 22.5]
