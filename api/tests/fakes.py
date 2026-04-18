"""Fake DB/publisher used by API tests.

Dispatches SQL calls by substring match. Works for both fetch_* (reads) and
execute (writes). Tests register canned behavior per SQL fragment.
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

    def _dispatch(self, sql: str, params: tuple[Any, ...]) -> Any:
        self.calls.append((sql, params))
        for fragment, fn in self.routes:
            if fragment in sql:
                return fn(params)
        raise AssertionError(f"no route registered for SQL: {sql[:80]}")

    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        rows = self._dispatch(sql, params)
        return rows if rows is not None else []

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        rows = self._dispatch(sql, params)
        if not rows:
            return None
        return rows[0] if isinstance(rows, list) else rows

    def execute(self, sql: str, params: tuple[Any, ...]) -> int:
        self._dispatch(sql, params)
        return 1

    def sql_contains(self, substring: str) -> bool:
        return any(substring in c[0] for c in self.calls)


@dataclass
class FakePublisher:
    published: list[tuple[str, str, int]] = field(default_factory=list)

    def publish(self, topic: str, payload: str, qos: int = 1) -> None:
        self.published.append((topic, payload, qos))
