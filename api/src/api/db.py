"""psycopg-backed DatabaseClient for the read API.

Exposes both read (fetch_all/fetch_one) and write (execute) methods so the
same pool serves Query and Mutation resolvers. Mutation calls belonging to
a single request are wrapped in a transaction via the pool's autocommit
default disabled — each `with pool.connection()` block is its own tx.
"""

from __future__ import annotations

from typing import Any

from psycopg_pool import ConnectionPool


class PgClient:
    def __init__(self, dsn: str, pool_min: int = 2, pool_max: int = 10) -> None:
        self.pool = ConnectionPool(
            dsn, min_size=pool_min, max_size=pool_max, open=False
        )

    def open(self) -> None:
        self.pool.open()
        self.pool.wait()

    def close(self) -> None:
        self.pool.close()

    # --- Reads ---

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    # --- Writes ---

    def execute(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount or 0
