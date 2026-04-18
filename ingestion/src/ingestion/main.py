"""Entry point for the ingestion service."""

from __future__ import annotations

import logging
import sys

from . import config, db, mqtt_client


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("ingestion")

    cfg = config.load()
    log.info(
        "starting ingestion: mqtt=%s:%s pg=%s patterns=%s",
        cfg.mqtt_host, cfg.mqtt_port,
        cfg.pg_dsn.split("@")[-1],  # hide credentials
        cfg.mqtt_subscribe_patterns,
    )

    executor = db.PgExecutor(
        cfg.pg_dsn, pool_min=cfg.pg_pool_min, pool_max=cfg.pg_pool_max
    )
    executor.open()
    try:
        mqtt_client.run(cfg, executor)
    finally:
        executor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
