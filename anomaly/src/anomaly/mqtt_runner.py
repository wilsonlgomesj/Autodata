"""MQTT subscriber → RollingScorer."""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import Iterable

import paho.mqtt.client as mqtt

from .scorer import RollingScorer, observations_from_payload


log = logging.getLogger(__name__)


def run_mqtt_loop(
    *,
    host: str,
    port: int,
    client_id: str,
    subscribe_patterns: Iterable[str],
    scorer: RollingScorer,
    site_id: str,
) -> None:
    client = mqtt.Client(
        client_id=client_id, protocol=mqtt.MQTTv5, clean_session=False,
    )

    def on_connect(c, u, f, rc, props=None):
        log.info("anomaly scorer connected: %s", rc)
        for p in subscribe_patterns:
            c.subscribe(p, qos=1)
            log.info("subscribed %s", p)

    def on_message(c, u, msg: mqtt.MQTTMessage):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            for site, sensor, metric, t, value in observations_from_payload(payload):
                if site != site_id:
                    continue
                result = scorer.observe(
                    site_id=site, sensor_id=sensor, metric=metric,
                    t_sample=t, value=value,
                )
                if result and result.is_anomaly:
                    log.info(
                        "ANOMALY sensor=%s metric=%s score=%.3f features=%s",
                        sensor, metric, result.score, result.features,
                    )
        except Exception:
            log.exception("scoring error on topic=%s", msg.topic)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)

    def shutdown(s, f):
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    client.loop_forever(retry_first_connection=True)
