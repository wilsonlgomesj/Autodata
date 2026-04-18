"""Store-and-forward SQLite buffer.

Implements the contract from docs/conventions.md:
  - Write before send.
  - Only delete after PUBACK (sent=1).
  - FIFO eviction only when disk pressure > 80% (simulated by max_rows cap).

Schema:
    CREATE TABLE buffer (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      t_sample TEXT NOT NULL,
      topic TEXT NOT NULL,
      payload TEXT NOT NULL,
      sent INTEGER NOT NULL DEFAULT 0
    )
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    t_sample TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS buffer_sent_id ON buffer(sent, id);
"""


class StoreForwardBuffer:
    def __init__(self, db_path: str | Path, max_rows: int = 100_000) -> None:
        self.db_path = str(db_path)
        self.max_rows = max_rows
        self.conn = sqlite3.connect(
            self.db_path, isolation_level=None, check_same_thread=False
        )
        self.conn.executescript("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def enqueue(self, t_sample: str, topic: str, payload: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO buffer (t_sample, topic, payload) VALUES (?, ?, ?)",
            (t_sample, topic, payload),
        )
        row_id = cur.lastrowid

        # Enforce cap by evicting the oldest sent rows first; if none sent,
        # evict oldest unsent (lose data consciously rather than crash OOM).
        (count,) = cur.execute("SELECT count(*) FROM buffer").fetchone()
        if count > self.max_rows:
            excess = count - self.max_rows
            cur.execute(
                "DELETE FROM buffer WHERE id IN ("
                "  SELECT id FROM buffer ORDER BY sent DESC, id ASC LIMIT ?"
                ")",
                (excess,),
            )
        return row_id

    def pending(self, limit: int = 100) -> list[tuple[int, str, str, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, t_sample, topic, payload FROM buffer "
            "WHERE sent = 0 ORDER BY id LIMIT ?",
            (limit,),
        )
        return list(cur.fetchall())

    def mark_sent(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        self.conn.execute(
            "UPDATE buffer SET sent=1 WHERE id IN ("
            + ",".join("?" * len(ids))
            + ")",
            ids,
        )

    def purge_sent(self, keep_last_n: int = 1000) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM buffer WHERE sent=1 AND id NOT IN ("
            "  SELECT id FROM buffer WHERE sent=1 ORDER BY id DESC LIMIT ?"
            ")",
            (keep_last_n,),
        )
        return cur.rowcount or 0

    def stats(self) -> dict[str, int]:
        cur = self.conn.cursor()
        (pending,) = cur.execute("SELECT count(*) FROM buffer WHERE sent=0").fetchone()
        (sent,) = cur.execute("SELECT count(*) FROM buffer WHERE sent=1").fetchone()
        return {"pending": pending, "sent": sent}
