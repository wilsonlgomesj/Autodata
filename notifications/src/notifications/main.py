"""Entry point for the notification dispatcher service."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from .dispatcher import Dispatcher
from .mqtt_runner import run_mqtt_loop
from .notifiers import (
    EmailNotifier, SmsNotifier, SmtpConfig, VoiceNotifier, WebhookNotifier,
    StubSmsProvider, StubVoiceProvider,
)


class PgExecutor:
    def __init__(self, pool: ConnectionPool):
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


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("notifications")

    pg_dsn = _env("PG_DSN")
    if not pg_dsn:
        raise RuntimeError("PG_DSN is required")

    pool = ConnectionPool(pg_dsn, min_size=2, max_size=5, open=False)
    pool.open()
    pool.wait()

    executor = PgExecutor(pool)

    # Build notifiers. Real SMS/voice providers require credentials; if not
    # set, fall back to the stub so dev environments still function end-to-end.
    smtp = SmtpConfig(
        host=_env("SMTP_HOST", "mailhog"),
        port=int(_env("SMTP_PORT", "1025")),
        username=_env("SMTP_USERNAME"),
        password=_env("SMTP_PASSWORD"),
        use_tls=_env("SMTP_TLS", "false").lower() == "true",
        from_addr=_env("SMTP_FROM", "alerts@autodata.local"),
    )
    notifiers = {
        "email": EmailNotifier(smtp),
        "webhook": WebhookNotifier(),
        "sms": SmsNotifier(provider=StubSmsProvider()),
        "voice": VoiceNotifier(provider=StubVoiceProvider()),
    }

    dispatcher = Dispatcher(executor, notifiers)

    mqtt_host = _env("MQTT_HOST", "mqtt")
    mqtt_port = int(_env("MQTT_PORT", "1883"))
    patterns = tuple(
        p.strip() for p in _env(
            "MQTT_SUBSCRIBE_PATTERNS", "alert/+/+/+"
        ).split(",") if p.strip()
    )

    log.info(
        "notifications starting: mqtt=%s:%s pg=%s patterns=%s notifiers=%s",
        mqtt_host, mqtt_port, pg_dsn.split("@")[-1], patterns,
        list(notifiers.keys()),
    )

    try:
        run_mqtt_loop(
            host=mqtt_host,
            port=mqtt_port,
            client_id=f"svc-notifications-{os.getpid()}",
            subscribe_patterns=patterns,
            dispatcher=dispatcher,
        )
    finally:
        pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
