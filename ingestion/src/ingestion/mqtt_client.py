"""MQTT client wiring paho-mqtt to our handler.

Runs in the main thread blocking on loop_forever() with automatic reconnect.
Per-message errors are caught and logged; DLQ handling lives in handler.py.
"""

from __future__ import annotations

import logging
import signal
import ssl
import sys
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from .config import Config
from .handler import handle_message
from .persister import Executor


log = logging.getLogger(__name__)


@dataclass
class Runtime:
    config: Config
    executor: Executor
    client: mqtt.Client


def build_client(cfg: Config) -> mqtt.Client:
    client = mqtt.Client(
        client_id=cfg.mqtt_client_id,
        protocol=mqtt.MQTTv5,
        clean_session=False,  # resume session to avoid missed messages
    )

    if cfg.mqtt_username:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)

    if cfg.mqtt_tls:
        client.tls_set(
            ca_certs=cfg.mqtt_ca_cert,
            certfile=cfg.mqtt_client_cert,
            keyfile=cfg.mqtt_client_key,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    return client


def run(cfg: Config, executor: Executor) -> None:
    client = build_client(cfg)
    runtime = Runtime(cfg, executor, client)

    def on_connect(c: mqtt.Client, userdata, flags, reason_code, properties=None):
        log.info("MQTT connected: reason=%s", reason_code)
        for pattern in cfg.mqtt_subscribe_patterns:
            c.subscribe(pattern, qos=1)
            log.info("subscribed: %s", pattern)

    def on_disconnect(c, userdata, reason_code, properties=None):
        log.warning("MQTT disconnected: reason=%s", reason_code)

    def on_message(c, userdata, msg: mqtt.MQTTMessage):
        try:
            result = handle_message(
                executor=runtime.executor,
                topic=msg.topic,
                raw_payload=msg.payload,
                dead_letter_enabled=cfg.dead_letter_enabled,
            )
            if not result.ok:
                log.warning(
                    "message rejected: topic=%s reason=%s",
                    msg.topic, result.reason,
                )
        except Exception:
            log.exception("unhandled error on topic=%s", msg.topic)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)

    def shutdown(signum, frame):
        log.info("shutdown signal %s received", signum)
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    client.loop_forever(retry_first_connection=True)
