"""Cross-platform golden test: the expected canonical bytes hardcoded in
the C++ unit test must exactly match what the Python reference produces
for the same payload.

This lets us verify the contract without flashing hardware: if this test
passes AND the C++ unit test passes, both sides agree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "rtu" / "src"))

from rtu.signing import canonical_message_bytes  # type: ignore


GOLDEN_PAYLOAD = {
    "schema": "geo.telemetry.v1",
    "msg_id": "01HK00000000000000000000AA",
    "site": "mineradora-x-barragem-norte",
    "gateway": "gw-bx-001",
    "device": "rtu-bx-c1",
    "sensor": "pz-sec02-fund-01",
    "sensor_type": "piezometer_vw",
    "t_sample": "2026-04-18T13:45:03.123Z",
    "t_ingest": "2026-04-18T13:45:04.000Z",
    "seq": 1,
    "values": {
        "pressure_kpa": 312.4,
        "frequency_hz": 2345,
        "temp_c": 25.6,
    },
    "quality": {"code": "GOOD", "flags": []},
    "firmware": "rtu-fw",
    "sig": "ed25519:should-be-removed",
}


EXPECTED = (
    '{"device":"rtu-bx-c1","firmware":"rtu-fw","gateway":"gw-bx-001",'
    '"msg_id":"01HK00000000000000000000AA","quality":{"code":"GOOD",'
    '"flags":[]},"schema":"geo.telemetry.v1","sensor":"pz-sec02-fund-01",'
    '"sensor_type":"piezometer_vw","seq":1,"site":"mineradora-x-barragem-norte",'
    '"t_sample":"2026-04-18T13:45:03.123Z","values":{"frequency_hz":2345,'
    '"pressure_kpa":312.4,"temp_c":25.6}}'
)


def test_python_matches_expected_golden():
    produced = canonical_message_bytes(GOLDEN_PAYLOAD).decode("utf-8")
    assert produced == EXPECTED, (
        f"\nExpected:\n{EXPECTED}\n\nGot:\n{produced}"
    )


def test_cpp_test_file_contains_same_expected_string():
    """Belt-and-suspenders: ensure the C++ test's EXPECTED literal is
    actually the same string — otherwise the two sides could drift silently.
    """
    cpp_path = Path(__file__).parent / "test_canonical" / "test_canonical.cpp"
    body = cpp_path.read_text()
    # Find the C++ raw literal assembled via multi-line concatenation:
    # find every chunk between `"` and `"` after `EXPECTED =`, concatenate.
    m = re.search(
        r"\bEXPECTED\s*=\s*((?:\"(?:\\.|[^\"\\])*\"\s*)+);",
        body,
        re.DOTALL,
    )
    assert m, "could not find EXPECTED literal in C++ test"
    chunks = re.findall(r'"((?:\\.|[^"\\])*)"', m.group(1))
    cpp_expected = "".join(c.replace('\\"', '"').replace("\\\\", "\\") for c in chunks)
    assert cpp_expected == EXPECTED
