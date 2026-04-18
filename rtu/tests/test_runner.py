"""End-to-end RTU runner with a fake publisher.

Critically: also exercises the round-trip by feeding signed payloads produced
by the RTU into the ingestion verifier, to catch any divergence between the
canonical-bytes implementations on both sides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rtu.buffer import StoreForwardBuffer  # type: ignore
from rtu.runner import RTUConfig, Publisher, publish_sample, drain_buffer  # type: ignore
from rtu.signing import generate_keypair  # type: ignore


@dataclass
class FakePublisher(Publisher):
    connected: bool = True
    fail_next: bool = False
    published: list[tuple[str, str]] = field(default_factory=list)

    def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        if self.fail_next:
            self.fail_next = False
            return False
        if not self.connected:
            return False
        self.published.append((topic, payload))
        return True


def _mk_config(tmp_path: Path) -> tuple[RTUConfig, FakePublisher]:
    priv, _pub = generate_keypair()
    buf = StoreForwardBuffer(tmp_path / "buf.sqlite")
    cfg = RTUConfig(
        site="mineradora-x-barragem-norte",
        gateway="gw-bx-001",
        device="rtu-bx-c1",
        private_key=priv,
        buffer=buf,
    )
    return cfg, FakePublisher()


def test_publish_sample_writes_to_buffer_and_publishes(tmp_path):
    cfg, pub = _mk_config(tmp_path)
    row_id = publish_sample(
        cfg, pub,
        sensor="pz-sec02-fund-01",
        sensor_type="piezometer_vw",
        t_sample=datetime(2026, 1, 1, tzinfo=timezone.utc),
        seq=1,
        values={"pressure_kpa": 312.4, "frequency_hz": 2345.0, "temp_c": 25.6},
    )
    assert row_id >= 1
    assert len(pub.published) == 1

    topic, payload = pub.published[0]
    assert topic == (
        "tel/mineradora-x-barragem-norte/gw-bx-001/rtu-bx-c1/pz-sec02-fund-01/meas"
    )
    body = json.loads(payload)
    assert body["schema"] == "geo.telemetry.v1"
    assert body["sig"].startswith("ed25519:")

    # Sent state in buffer
    assert cfg.buffer.stats() == {"pending": 0, "sent": 1}
    cfg.buffer.close()


def test_failed_publish_leaves_row_pending(tmp_path):
    cfg, pub = _mk_config(tmp_path)
    pub.fail_next = True
    publish_sample(
        cfg, pub,
        sensor="pz-sec02-fund-01", sensor_type="piezometer_vw",
        t_sample=datetime(2026, 1, 1, tzinfo=timezone.utc),
        seq=1,
        values={"pressure_kpa": 312.4},
    )
    assert cfg.buffer.stats() == {"pending": 1, "sent": 0}
    # Recovery
    drain_buffer(cfg, pub, batch=10)
    assert cfg.buffer.stats() == {"pending": 0, "sent": 1}
    cfg.buffer.close()


def test_payload_passes_json_schema_validation(tmp_path):
    """Published payload must satisfy geo.telemetry.v1."""
    import sys
    REPO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from validate import Report, validate_payload  # type: ignore

    cfg, pub = _mk_config(tmp_path)
    publish_sample(
        cfg, pub,
        sensor="pz-sec02-fund-01", sensor_type="piezometer_vw",
        t_sample=datetime(2026, 4, 18, 13, 45, tzinfo=timezone.utc),
        seq=42,
        values={"pressure_kpa": 312.4, "frequency_hz": 2345.0, "temp_c": 25.6},
    )
    payload = json.loads(pub.published[0][1])
    report = Report()
    validate_payload(payload, report)
    assert report.ok(), report.errors
    cfg.buffer.close()


def test_backend_verifier_accepts_rtu_signature(tmp_path):
    """Cross-module: RTU signs, ingestion's verify_payload must accept.

    Guards against silent divergence between signing.py and signature.py.
    """
    from ingestion.signature import verify_payload  # type: ignore

    priv, pub_key = generate_keypair()
    buf = StoreForwardBuffer(tmp_path / "buf.sqlite")
    cfg = RTUConfig(
        site="mineradora-x-barragem-norte",
        gateway="gw-bx-001",
        device="rtu-bx-c1",
        private_key=priv,
        buffer=buf,
    )
    fake_pub = FakePublisher()
    publish_sample(
        cfg, fake_pub,
        sensor="pz-sec02-fund-01", sensor_type="piezometer_vw",
        t_sample=datetime(2026, 4, 18, 13, 45, tzinfo=timezone.utc),
        seq=42,
        values={"pressure_kpa": 312.4, "frequency_hz": 2345.0, "temp_c": 25.6},
    )
    payload = json.loads(fake_pub.published[0][1])

    def resolver(site, device):
        return pub_key if (site == cfg.site and device == cfg.device) else None

    assert verify_payload(payload, resolver) is True

    # Unknown device must return False.
    def empty(s, d):
        return None
    assert verify_payload(payload, empty) is False

    # Tampered payload after signing must fail.
    payload["values"]["pressure_kpa"] = 999.9
    assert verify_payload(payload, resolver) is False
    buf.close()
