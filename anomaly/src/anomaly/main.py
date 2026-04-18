"""Entry point: load active models for the configured site, subscribe to
telemetry, score incoming samples in real time.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from psycopg_pool import ConnectionPool

from .mqtt_runner import run_mqtt_loop
from .scorer import RollingScorer
from .store import ModelStore


class PgExecutor:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def execute(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount or 0

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("anomaly")

    pg_dsn = os.environ["PG_DSN"]
    site_id = os.environ["SITE_ID"]
    mqtt_host = os.environ.get("MQTT_HOST", "mqtt")
    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
    window_size = int(os.environ.get("WINDOW_SIZE", "24"))

    pool = ConnectionPool(pg_dsn, min_size=2, max_size=5, open=False)
    pool.open()
    pool.wait()
    executor = PgExecutor(pool)

    store = ModelStore(executor)
    models = store.load_active_for_site(site_id)

    if not models:
        log.warning(
            "no active anomaly models found for site=%s; running as no-op "
            "(train and persist models first).", site_id,
        )

    scorer = RollingScorer(
        models=models, window_size=window_size, executor=executor,
    )

    patterns = ("tel/+/+/+/+/meas",)
    log.info(
        "anomaly scorer starting: site=%s models=%d window=%d mqtt=%s:%s",
        site_id, len(models), window_size, mqtt_host, mqtt_port,
    )

    try:
        run_mqtt_loop(
            host=mqtt_host, port=mqtt_port,
            client_id=f"svc-anomaly-{os.getpid()}",
            subscribe_patterns=patterns,
            scorer=scorer, site_id=site_id,
        )
    finally:
        pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
