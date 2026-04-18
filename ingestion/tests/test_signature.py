"""Tests for Ed25519 verification integration in the ingestion handler."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "rtu" / "src"))

from ingestion.handler import handle_message  # type: ignore
from ingestion.signature import verify_payload  # type: ignore
from rtu.payload import build_measurement_payload  # type: ignore
from rtu.signing import generate_keypair  # type: ignore
from datetime import datetime, timezone


@dataclass
class FakeExecutor:
    calls: list = field(default_factory=list)

    def execute_many(self, sql, rows):
        rows = list(rows)
        self.calls.append((sql, rows))
        return len(rows)


def _signed_payload(priv, *, seq=1, values=None):
    return build_measurement_payload(
        site="mineradora-x-barragem-norte",
        gateway="gw-bx-001",
        device="rtu-bx-c1",
        sensor="pz-sec02-fund-01",
        sensor_type="piezometer_vw",
        t_sample=datetime(2026, 4, 18, 13, 45, tzinfo=timezone.utc),
        seq=seq,
        values=values or {"pressure_kpa": 312.4, "frequency_hz": 2345.0, "temp_c": 25.6},
        private_key=priv,
    )


def _topic_for(payload):
    return (
        f"tel/{payload['site']}/{payload['gateway']}/"
        f"{payload['device']}/{payload['sensor']}/meas"
    )


def test_verifier_accepts_valid_rtu_signature():
    priv, pub_key = generate_keypair()
    payload = _signed_payload(priv)

    executor = FakeExecutor()
    resolver = lambda s, d: pub_key

    def verifier(p):
        return verify_payload(p, resolver)

    r = handle_message(
        executor, _topic_for(payload), json.dumps(payload), verifier=verifier
    )
    assert r.ok is True
    assert r.rows_inserted > 0


def test_verifier_rejects_wrong_key_to_dead_letter():
    priv_a, _ = generate_keypair()
    _, wrong_pub = generate_keypair()
    payload = _signed_payload(priv_a)

    executor = FakeExecutor()
    resolver = lambda s, d: wrong_pub

    def verifier(p):
        return verify_payload(p, resolver)

    r = handle_message(
        executor, _topic_for(payload), json.dumps(payload), verifier=verifier
    )
    assert r.ok is False
    assert r.reason == "signature_invalid"
    # Must have written to dead_letter
    assert any("dead_letter" in c[0] for c in executor.calls)


def test_verifier_rejects_unknown_device():
    priv, _ = generate_keypair()
    payload = _signed_payload(priv)

    executor = FakeExecutor()
    resolver = lambda s, d: None

    def verifier(p):
        return verify_payload(p, resolver)

    r = handle_message(
        executor, _topic_for(payload), json.dumps(payload), verifier=verifier
    )
    assert r.ok is False
    assert r.reason == "signature_invalid"


def test_no_verifier_skips_signature_check():
    # When verifier=None, the handler must not enforce signatures (useful
    # for bootstrap / dev).
    priv, _ = generate_keypair()
    payload = _signed_payload(priv)
    # Corrupt the sig — handler should still accept because verifier=None.
    payload["sig"] = "ed25519:" + "A" * 88
    executor = FakeExecutor()
    r = handle_message(
        executor, _topic_for(payload), json.dumps(payload), verifier=None
    )
    assert r.ok is True
