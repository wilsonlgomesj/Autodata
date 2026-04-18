#!/usr/bin/env python3
"""Smoke test — ensures the validator rejects known-bad inputs.

Run: python3 tools/test_validator.py
Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from validate import Report, validate_payload, validate_plan  # type: ignore


GOOD_PAYLOAD = json.loads(
    (REPO_ROOT / "examples" / "payloads" / "piezometer_vw_good.json").read_text()
)


def expect_fail(description: str, mutate) -> bool:
    payload = copy.deepcopy(GOOD_PAYLOAD)
    mutate(payload)
    r = Report()
    validate_payload(payload, r)
    if r.ok():
        print(f"FAIL [{description}]: expected validation error, got OK")
        return False
    print(f"OK   [{description}]: rejected as expected")
    return True


def main() -> int:
    passed = True

    # Unknown schema
    passed &= expect_fail(
        "unknown schema",
        lambda p: p.__setitem__("schema", "geo.telemetry.v99"),
    )

    # Invalid msg_id (wrong length)
    passed &= expect_fail(
        "invalid msg_id",
        lambda p: p.__setitem__("msg_id", "SHORT"),
    )

    # Invalid identifier (uppercase)
    passed &= expect_fail(
        "uppercase identifier in site",
        lambda p: p.__setitem__("site", "INVALID-SITE"),
    )

    # sensor_type mismatch with values keys
    def mutate_values(p):
        p["values"] = {"displacement_mm": 1.0}
    passed &= expect_fail("values keys not in sensor_type", mutate_values)

    # quality.code unknown
    passed &= expect_fail(
        "unknown quality code",
        lambda p: p.__setitem__("quality", {"code": "UNKNOWN"}),
    )

    # Missing required field
    def drop_sig(p):
        del p["sig"]
    passed &= expect_fail("missing sig", drop_sig)

    # Plan: duplicate sensor id
    plan = {
        "schema": "geo.instrumentation.v1",
        "site": {"id": "x", "org_id": "o", "display_name": "X",
                 "country": "BR", "timezone": "America/Sao_Paulo"},
        "structures": [{
            "id": "s1", "kind": "earth_dam", "display_name": "S1",
            "sections": [{"id": "sec-01", "display_name": "S1"}],
        }],
        "devices": [
            {"id": "gw1", "kind": "gateway"},
            {"id": "rtu1", "kind": "rtu", "parent_gateway": "gw1"},
        ],
        "sensors": [
            {"id": "pz-sec01-01", "type": "piezometer_vw",
             "structure": "s1", "section": "sec-01", "device": "rtu1"},
            {"id": "pz-sec01-01", "type": "piezometer_vw",
             "structure": "s1", "section": "sec-01", "device": "rtu1"},
        ],
    }
    r = Report()
    validate_plan(plan, r)
    if r.ok() or not any("duplicate sensor" in e for e in r.errors):
        print("FAIL [plan duplicate sensor]: not caught")
        passed = False
    else:
        print("OK   [plan duplicate sensor]: rejected as expected")

    # Plan: non-monotonic above-thresholds
    plan2 = copy.deepcopy(plan)
    plan2["sensors"] = [plan["sensors"][0]]
    plan2["thresholds"] = [{
        "sensor": "pz-sec01-01",
        "metric": "pressure_kpa",
        "effective_from": "2024-01-01T00:00:00Z",
        "direction": "above",
        "hysteresis_pct": 5.0,
        "levels": {"atencao": 500, "alerta": 400, "emergencia_n1": 600, "emergencia_n2": 700},
        "approved_by": "x", "approval_ref": "y",
    }]
    r = Report()
    validate_plan(plan2, r)
    if r.ok() or not any("not monotonic" in e for e in r.errors):
        print("FAIL [plan non-monotonic levels]: not caught")
        passed = False
    else:
        print("OK   [plan non-monotonic levels]: rejected as expected")

    print()
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
