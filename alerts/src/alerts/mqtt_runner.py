"""MQTT wiring for the alert service. Isolated so that the core
AlertService in service.py stays testable without paho-mqtt installed.
"""

from __future__ import annotations

import json
import logging
import signal
import ssl
import sys
from typing import Iterable

import paho.mqtt.client as mqtt

from .service import AlertService


log = logging.getLogger(__name__)


def _on_message_factory(service: AlertService):
    def _on_message(c, userdata, msg: mqtt.MQTTMessage):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            service.handle_payload(payload)
        except Exception:
            log.exception("alert engine error on topic=%s", msg.topic)
    return _on_message


def run_mqtt_loop(
    host: str,
    port: int,
    client_id: str,
    subscribe_patterns: Iterable[str],
    service: AlertService,
    username: str | None = None,
    password: str | None = None,
    use_tls: bool = False,
) -> None:
    client = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv5,
        clean_session=False,
    )
    if username:
        client.username_pw_set(username, password)
    if use_tls:
        client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)

    def on_connect(c, u, f, rc, props=None):
        log.info("alert engine connected: %s", rc)
        for p in subscribe_patterns:
            c.subscribe(p, qos=1)
            log.info("subscribed %s", p)

    client.on_connect = on_connect
    client.on_message = _on_message_factory(service)
    client.connect(host, port, keepalive=60)

    def shutdown(s, f):
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    client.loop_forever(retry_first_connection=True)
