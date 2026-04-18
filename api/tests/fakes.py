"""Fake DatabaseClient backed by in-memory dispatch table.

Tests register canned responses per SQL fingerprint. Lets us exercise the
Repository and GraphQL resolvers without a real database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FakeDatabaseClient:
    """Dispatches SQL calls by substring match to a canned response function."""
    routes: list[tuple[str, Callable]] = field(default_factory=list)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def on(self, sql_substring: str, response_fn: Callable) -> None:
        self.routes.append((sql_substring, response_fn))

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        self.calls.append((sql, params))
        for fragment, fn in self.routes:
            if fragment in sql:
                return fn(params)
        raise AssertionError(f"no route registered for SQL: {sql[:80]}")

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None
