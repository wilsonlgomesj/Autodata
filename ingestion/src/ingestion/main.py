"""Entry point for the ingestion service."""

from __future__ import annotations

import logging
import os
import sys

from . import config, db, mqtt_client


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("ingestion")

    cfg = config.load()
    require_sig = os.environ.get("REQUIRE_SIGNATURE", "false").lower() == "true"

    log.info(
        "starting ingestion: mqtt=%s:%s pg=%s patterns=%s require_sig=%s",
        cfg.mqtt_host, cfg.mqtt_port,
        cfg.pg_dsn.split("@")[-1],
        cfg.mqtt_subscribe_patterns,
        require_sig,
    )

    executor = db.PgExecutor(
        cfg.pg_dsn, pool_min=cfg.pg_pool_min, pool_max=cfg.pg_pool_max
    )
    executor.open()

    verifier = None
    if require_sig:
        from .signature import PgPublicKeyResolver, verify_payload
        resolver = PgPublicKeyResolver(executor.pool)
        def verifier(payload):  # type: ignore
            return verify_payload(payload, resolver)
        log.info("Ed25519 signature verification ENABLED")

    try:
        mqtt_client.run(cfg, executor, verifier=verifier)
    finally:
        executor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
