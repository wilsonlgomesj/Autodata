"""Tests for Ed25519 signing/verifying and canonical bytes."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from rtu.signing import (  # type: ignore
    canonical_message_bytes,
    generate_keypair,
    public_key_to_pem,
    sign_payload,
    verify_signature,
)


def test_canonical_bytes_excludes_sig_and_t_ingest():
    p = {
        "schema": "geo.telemetry.v1",
        "msg_id": "0" * 26,
        "site": "a", "gateway": "b", "device": "c", "sensor": "d",
        "values": {"x": 1, "a": 2},
        "sig": "ed25519:should-be-ignored",
        "t_ingest": "2026-01-01T00:00:00.000Z",
    }
    b = canonical_message_bytes(p)
    text = b.decode("utf-8")
    assert "sig" not in text
    assert "t_ingest" not in text
    # Keys are sorted deterministically (a before x in values)
    assert text.index('"a":2') < text.index('"x":1')


def test_canonical_bytes_is_stable():
    p1 = {"b": 2, "a": {"y": 1, "x": 2}}
    p2 = {"a": {"x": 2, "y": 1}, "b": 2}
    assert canonical_message_bytes(p1) == canonical_message_bytes(p2)


def test_sign_and_verify_roundtrip():
    priv, pub = generate_keypair()
    payload = {
        "schema": "geo.telemetry.v1",
        "msg_id": "0" * 26,
        "site": "s", "gateway": "g", "device": "d", "sensor": "pz-1",
        "sensor_type": "piezometer_vw",
        "t_sample": "2026-01-01T00:00:00.000Z",
        "t_ingest": None,
        "seq": 1,
        "values": {"pressure_kpa": 312.4},
        "quality": {"code": "GOOD", "flags": []},
        "firmware": "test-fw",
    }
    payload["sig"] = sign_payload(payload, priv)
    assert verify_signature(payload, pub) is True


def test_verify_fails_on_mutated_payload():
    priv, pub = generate_keypair()
    payload = {
        "schema": "geo.telemetry.v1",
        "msg_id": "0" * 26,
        "site": "s", "gateway": "g", "device": "d", "sensor": "pz-1",
        "sensor_type": "piezometer_vw",
        "t_sample": "2026-01-01T00:00:00.000Z",
        "t_ingest": None,
        "seq": 1,
        "values": {"pressure_kpa": 312.4},
        "quality": {"code": "GOOD", "flags": []},
        "firmware": "test-fw",
    }
    payload["sig"] = sign_payload(payload, priv)
    # Tamper with a measurement value — signature must fail.
    payload["values"]["pressure_kpa"] = 999.9
    assert verify_signature(payload, pub) is False


def test_verify_fails_on_malformed_sig():
    _, pub = generate_keypair()
    payload = {"sig": "not-a-signature", "a": 1}
    assert verify_signature(payload, pub) is False


def test_verify_ignores_t_ingest_field():
    """The backend stamps t_ingest after receiving; sig must still verify."""
    priv, pub = generate_keypair()
    payload = {
        "schema": "geo.telemetry.v1",
        "msg_id": "0" * 26,
        "site": "s", "gateway": "g", "device": "d", "sensor": "pz-1",
        "sensor_type": "piezometer_vw",
        "t_sample": "2026-01-01T00:00:00.000Z",
        "t_ingest": None,
        "seq": 1,
        "values": {"pressure_kpa": 312.4},
        "quality": {"code": "GOOD", "flags": []},
        "firmware": "test-fw",
    }
    payload["sig"] = sign_payload(payload, priv)
    # Backend fills t_ingest; verification must still succeed.
    payload["t_ingest"] = "2026-01-01T00:00:05.000Z"
    assert verify_signature(payload, pub) is True


def test_pem_roundtrip_keys():
    priv, pub = generate_keypair()
    pem = public_key_to_pem(pub)
    assert b"BEGIN PUBLIC KEY" in pem
