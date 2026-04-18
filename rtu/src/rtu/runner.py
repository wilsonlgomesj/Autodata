"""RTU runner: sample sensor → build payload → sign → buffer → publish.

Single-site, multi-sensor. Designed for the dev stack and for load testing.
Real production RTUs run on a microcontroller — this is the Python
reference implementation that matches the contract exactly.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .buffer import StoreForwardBuffer
from .payload import build_measurement_payload


log = logging.getLogger(__name__)


@dataclass
class RTUConfig:
    site: str
    gateway: str
    device: str
    private_key: Ed25519PrivateKey
    buffer: StoreForwardBuffer
    firmware: str = "rtu-fw-2.4.1"


class Publisher:
    """Minimal publish interface so the runner can accept any transport."""

    def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        raise NotImplementedError


def publish_sample(
    config: RTUConfig,
    publisher: Publisher | None,
    *,
    sensor: str,
    sensor_type: str,
    t_sample: datetime,
    seq: int,
    values: dict,
    quality_code: str = "GOOD",
) -> int:
    """Build + sign + buffer + (attempt) publish a single sample.

    Always persists to the local buffer BEFORE attempting to publish.
    Marks as sent only on successful publish. Returns the buffer row id.
    """
    payload = build_measurement_payload(
        site=config.site,
        gateway=config.gateway,
        device=config.device,
        sensor=sensor,
        sensor_type=sensor_type,
        t_sample=t_sample,
        seq=seq,
        values=values,
        quality_code=quality_code,
        firmware=config.firmware,
        private_key=config.private_key,
    )
    topic = (
        f"tel/{config.site}/{config.gateway}/{config.device}/{sensor}/meas"
    )
    body = json.dumps(payload, ensure_ascii=False)

    row_id = config.buffer.enqueue(payload["t_sample"], topic, body)
    if publisher is not None:
        try:
            ok = publisher.publish(topic, body, qos=1)
        except Exception:
            log.exception("publish failed for topic %s", topic)
            ok = False
        if ok:
            config.buffer.mark_sent([row_id])
    return row_id


def drain_buffer(config: RTUConfig, publisher: Publisher, batch: int = 100) -> int:
    """Attempt to publish pending buffered messages. Returns count sent."""
    sent_ids: list[int] = []
    for row_id, _t, topic, payload in config.buffer.pending(limit=batch):
        try:
            ok = publisher.publish(topic, payload, qos=1)
        except Exception:
            log.exception("drain publish failed id=%s", row_id)
            break
        if not ok:
            break
        sent_ids.append(row_id)
    config.buffer.mark_sent(sent_ids)
    return len(sent_ids)
