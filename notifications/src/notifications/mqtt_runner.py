"""MQTT runner: subscribes to alert/+/+/+ and feeds the dispatcher."""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import Iterable

import paho.mqtt.client as mqtt

from .dispatcher import Dispatcher


log = logging.getLogger(__name__)


def run_mqtt_loop(
    *,
    host: str,
    port: int,
    client_id: str,
    subscribe_patterns: Iterable[str],
    dispatcher: Dispatcher,
) -> None:
    client = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv5,
        clean_session=False,
    )

    def on_connect(c, u, f, rc, props=None):
        log.info("notifications connected: %s", rc)
        for p in subscribe_patterns:
            c.subscribe(p, qos=1)
            log.info("subscribed %s", p)

    def on_message(c, u, msg: mqtt.MQTTMessage):
        try:
            alert = json.loads(msg.payload.decode("utf-8"))
            if alert.get("schema") != "geo.alert.v1":
                log.warning("ignoring non-alert schema %s", alert.get("schema"))
                return
            result = dispatcher.dispatch(alert)
            log.info(
                "alert=%s dispatch sent=%d failed=%d",
                alert.get("msg_id"), result.sent, result.failed,
            )
        except Exception:
            log.exception("dispatch error on topic=%s", msg.topic)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)

    def shutdown(s, f):
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    client.loop_forever(retry_first_connection=True)
