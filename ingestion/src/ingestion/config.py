"""Configuration for the ingestion service.

Reads from environment variables. No config file — 12-factor style.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # MQTT
    mqtt_host: str
    mqtt_port: int
    mqtt_client_id: str
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_tls: bool
    mqtt_ca_cert: str | None
    mqtt_client_cert: str | None
    mqtt_client_key: str | None
    mqtt_subscribe_patterns: tuple[str, ...]

    # Postgres
    pg_dsn: str
    pg_pool_min: int
    pg_pool_max: int

    # Ingestion behavior
    batch_size: int
    batch_flush_ms: int
    dead_letter_enabled: bool


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"Missing required env var {name}")
    return v


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def load() -> Config:
    patterns = os.environ.get(
        "MQTT_SUBSCRIBE_PATTERNS",
        "tel/+/+/+/+/meas,tel/+/+/+/+/burst",
    )
    return Config(
        mqtt_host=_env("MQTT_HOST", "localhost"),
        mqtt_port=_env_int("MQTT_PORT", 1883),
        mqtt_client_id=_env("MQTT_CLIENT_ID", "svc-ingestion"),
        mqtt_username=_env("MQTT_USERNAME"),
        mqtt_password=_env("MQTT_PASSWORD"),
        mqtt_tls=_env_bool("MQTT_TLS", False),
        mqtt_ca_cert=_env("MQTT_CA_CERT"),
        mqtt_client_cert=_env("MQTT_CLIENT_CERT"),
        mqtt_client_key=_env("MQTT_CLIENT_KEY"),
        mqtt_subscribe_patterns=tuple(p.strip() for p in patterns.split(",") if p.strip()),
        pg_dsn=_env(
            "PG_DSN",
            "postgresql://postgres:pg@localhost:5432/postgres",
            required=True,
        ),
        pg_pool_min=_env_int("PG_POOL_MIN", 2),
        pg_pool_max=_env_int("PG_POOL_MAX", 10),
        batch_size=_env_int("BATCH_SIZE", 500),
        batch_flush_ms=_env_int("BATCH_FLUSH_MS", 1000),
        dead_letter_enabled=_env_bool("DEAD_LETTER_ENABLED", True),
    )
