"""Entry point for the alert engine service."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg
from psycopg_pool import ConnectionPool

from .emitter import AlertEmitter
from .mqtt_runner import run_mqtt_loop
from .service import AlertService
from .thresholds import ThresholdCache


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"missing env var {name}")
    return v


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


class PsycopgExecutor:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def execute_many(self, sql: str, rows):
        import re
        translated = re.sub(r"\$(\d+)", "%s", sql)
        rows_list = list(rows)
        if not rows_list:
            return 0
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(translated, rows_list)
        return len(rows_list)


class PahoPublisher:
    def __init__(self, client: mqtt.Client):
        self.client = client

    def publish(self, topic: str, payload: str, qos: int = 1) -> None:
        info = self.client.publish(topic, payload, qos=qos)
        info.wait_for_publish(timeout=5)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("alerts")

    rules_path = Path(_env("RULES_PATH", "/app/rules"))
    site_id = _env("SITE_ID", required=True)
    pg_dsn = _env("PG_DSN", required=True)
    mqtt_host = _env("MQTT_HOST", "localhost")
    mqtt_port = int(_env("MQTT_PORT", "1883"))
    patterns = tuple(
        p.strip() for p in _env(
            "MQTT_SUBSCRIBE_PATTERNS", "tel/+/+/+/+/meas"
        ).split(",") if p.strip()
    )

    pool = ConnectionPool(pg_dsn, min_size=2, max_size=5, open=False)
    pool.open()
    pool.wait()

    # Publish client (separate from subscribe client to avoid re-entry issues).
    pub_client = mqtt.Client(
        client_id=f"svc-alert-pub-{os.getpid()}",
        protocol=mqtt.MQTTv5,
    )
    pub_client.connect(mqtt_host, mqtt_port, keepalive=60)
    pub_client.loop_start()

    executor = PsycopgExecutor(pool)
    publisher = PahoPublisher(pub_client)
    emitter = AlertEmitter(executor, publisher)

    cache = ThresholdCache(pool)
    from .evaluator import RuleEvaluator
    from .rules import load_rules_from_dir, load_rules_from_file

    if rules_path.is_dir():
        ruleset = load_rules_from_dir(rules_path)
    else:
        ruleset = load_rules_from_file(rules_path)

    evaluator = RuleEvaluator(
        ruleset.rules, thresholds_for=cache.as_callable(site_id)
    )
    service = AlertService(
        rules_path=rules_path,
        evaluator=evaluator,
        emitter=emitter,
    )
    # Replace the fresh-loaded ruleset with the evaluator-attached one
    service.ruleset = ruleset

    log.info(
        "alert engine starting: rules=%s site=%s mqtt=%s:%s pg=%s",
        rules_path, site_id, mqtt_host, mqtt_port, pg_dsn.split("@")[-1],
    )

    try:
        run_mqtt_loop(
            host=mqtt_host,
            port=mqtt_port,
            client_id=f"svc-alert-sub-{os.getpid()}",
            subscribe_patterns=patterns,
            service=service,
        )
    finally:
        pub_client.loop_stop()
        pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
