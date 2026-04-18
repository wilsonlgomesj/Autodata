"""Entry point: run the RTU simulator against an MQTT broker.

Configuration via env vars:
  SITE, GATEWAY, DEVICE        identifiers
  PRIVATE_KEY_PEM              path to PEM file
  BUFFER_PATH                  SQLite buffer path
  MQTT_HOST, MQTT_PORT         broker address
  INTERVAL_S                   seconds between samples (default 15)
  SENSORS                      comma-separated 'sensor_id:sensor_type' pairs
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

from .buffer import StoreForwardBuffer
from .payload import new_ulid  # noqa: F401 — used indirectly, keeps dep visible
from .runner import RTUConfig, Publisher, drain_buffer, publish_sample
from .signing import generate_keypair, load_private_key_pem, private_key_to_pem
from .simulator import PIEZOMETER_VW, SensorProfile, iter_samples


class PahoPublisher(Publisher):
    def __init__(self, client: mqtt.Client) -> None:
        self.client = client
        self.connected = False
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect

    def _on_connect(self, c, u, f, rc, props=None):
        self.connected = True

    def _on_disconnect(self, c, u, rc, props=None):
        self.connected = False

    def publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        if not self.connected:
            return False
        info = self.client.publish(topic, payload, qos=qos)
        try:
            info.wait_for_publish(timeout=5)
        except RuntimeError:
            return False
        return info.rc == mqtt.MQTT_ERR_SUCCESS


def _load_or_generate_key(path: str | None) -> tuple:
    if path and Path(path).exists():
        return load_private_key_pem(Path(path)), None
    priv, pub = generate_keypair()
    return priv, pub  # caller may print the PEM for provisioning


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("rtu")

    site = os.environ.get("SITE", "mineradora-x-barragem-norte")
    gateway = os.environ.get("GATEWAY", "gw-bx-001")
    device = os.environ.get("DEVICE", "rtu-bx-c1")
    interval = float(os.environ.get("INTERVAL_S", "15"))
    mqtt_host = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
    buffer_path = os.environ.get("BUFFER_PATH", "/tmp/rtu_buffer.sqlite")
    key_path = os.environ.get("PRIVATE_KEY_PEM")

    priv, pub = _load_or_generate_key(key_path)
    if pub is not None:
        # Generated a fresh key because PRIVATE_KEY_PEM was unset. Print both
        # PEMs so the operator can provision them in Postgres (geo.device)
        # and persist them for restarts.
        from .signing import public_key_to_pem
        log.warning(
            "generated ephemeral Ed25519 keypair; provision in geo.device "
            "and set PRIVATE_KEY_PEM to persist.\n"
            "PUBLIC KEY:\n%s",
            public_key_to_pem(pub).decode(),
        )

    buffer = StoreForwardBuffer(buffer_path)
    config = RTUConfig(
        site=site, gateway=gateway, device=device,
        private_key=priv, buffer=buffer,
    )

    client = mqtt.Client(
        client_id=f"rtu-sim-{device}",
        protocol=mqtt.MQTTv5,
    )
    publisher = PahoPublisher(client)
    client.connect(mqtt_host, mqtt_port, keepalive=60)
    client.loop_start()

    profiles: list[SensorProfile] = [PIEZOMETER_VW]

    stop = False

    def _shutdown(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    seq = 0
    log.info("RTU starting: site=%s device=%s interval=%ss", site, device, interval)
    try:
        while not stop:
            seq += 1
            now = datetime.now(timezone.utc)
            for profile in profiles:
                values = profile.values_at(now, __import__("random").Random(seq))
                publish_sample(
                    config, publisher,
                    sensor=profile.sensor_id,
                    sensor_type=profile.sensor_type,
                    t_sample=now,
                    seq=seq,
                    values=values,
                )
            drain_buffer(config, publisher, batch=100)
            time.sleep(interval)
    finally:
        client.loop_stop()
        buffer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
