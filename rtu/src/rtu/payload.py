"""Build geo.telemetry.v1 payloads from a sample, then sign them."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .signing import sign_payload


_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    return "".join(secrets.choice(_ULID_ALPHABET) for _ in range(26))


def rfc3339_ms(t: datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t = t.astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def build_measurement_payload(
    *,
    site: str,
    gateway: str,
    device: str,
    sensor: str,
    sensor_type: str,
    t_sample: datetime,
    seq: int,
    values: dict[str, Any],
    quality_code: str = "GOOD",
    quality_flags: list[str] | None = None,
    firmware: str = "rtu-fw-2.4.1",
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Assemble a schema-valid payload and sign it with Ed25519."""
    payload: dict[str, Any] = {
        "schema": "geo.telemetry.v1",
        "msg_id": new_ulid(),
        "site": site,
        "gateway": gateway,
        "device": device,
        "sensor": sensor,
        "sensor_type": sensor_type,
        "t_sample": rfc3339_ms(t_sample),
        "t_ingest": None,
        "seq": seq,
        "values": values,
        "quality": {
            "code": quality_code,
            "flags": quality_flags or [],
        },
        "firmware": firmware,
    }
    # Sign over canonical form excluding sig + t_ingest; attach sig last.
    payload["sig"] = sign_payload(payload, private_key)
    return payload
