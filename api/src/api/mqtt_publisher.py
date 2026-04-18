"""Thin MQTT publisher used by the GraphQL issueCommand mutation.

Isolated in its own module so API tests can run without paho-mqtt.
"""

from __future__ import annotations

import paho.mqtt.client as mqtt


class PahoPublisher:
    def __init__(self, client: mqtt.Client) -> None:
        self.client = client

    def publish(self, topic: str, payload: str, qos: int = 1) -> None:
        info = self.client.publish(topic, payload, qos=qos)
        info.wait_for_publish(timeout=5)


def build_publisher(
    host: str, port: int, client_id: str = "api-cmd"
) -> PahoPublisher:
    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return PahoPublisher(client)
