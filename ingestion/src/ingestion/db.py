"""Postgres driver adapter implementing the Executor protocol.

Uses psycopg (v3). Parameters use positional $1..$N style in SQL to match the
Executor protocol; psycopg expects %s placeholders, so we translate on the fly.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

import psycopg
from psycopg_pool import ConnectionPool


_PARAM_RE = re.compile(r"\$(\d+)")


def _translate(sql: str) -> str:
    """Convert $1..$N placeholders to %s for psycopg."""
    return _PARAM_RE.sub("%s", sql)


class PgExecutor:
    def __init__(self, dsn: str, pool_min: int = 2, pool_max: int = 10):
        self.pool = ConnectionPool(
            dsn, min_size=pool_min, max_size=pool_max, open=False
        )

    def open(self) -> None:
        self.pool.open()
        self.pool.wait()

    def close(self) -> None:
        self.pool.close()

    def execute_many(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        translated = _translate(sql)
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(translated, rows)
                # psycopg's rowcount after executemany reflects the last
                # statement only in server-side mode; use returning for an
                # accurate count if needed. For ingestion metrics we trust
                # the input length minus any ON CONFLICT skips — the DB will
                # silently drop duplicates. Good-enough count: len(rows).
                return len(rows)
