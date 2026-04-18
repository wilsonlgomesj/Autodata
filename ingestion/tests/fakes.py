"""In-memory fake Executor for unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class RecordedCall:
    sql: str
    rows: list[tuple[Any, ...]]


@dataclass
class FakeExecutor:
    calls: list[RecordedCall] = field(default_factory=list)
    raise_on_sql_substring: str | None = None

    def execute_many(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> int:
        rows_list = list(rows)
        if self.raise_on_sql_substring and self.raise_on_sql_substring in sql:
            raise RuntimeError("forced failure for test")
        self.calls.append(RecordedCall(sql=sql, rows=rows_list))
        return len(rows_list)

    def sql_contains(self, substring: str) -> bool:
        return any(substring in c.sql for c in self.calls)

    def rows_for(self, substring: str) -> list[tuple[Any, ...]]:
        out: list[tuple[Any, ...]] = []
        for c in self.calls:
            if substring in c.sql:
                out.extend(c.rows)
        return out
