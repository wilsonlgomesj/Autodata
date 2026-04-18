"""Tests for store-and-forward buffer."""

from __future__ import annotations

from pathlib import Path

from rtu.buffer import StoreForwardBuffer  # type: ignore


def test_enqueue_and_mark_sent(tmp_path: Path):
    buf = StoreForwardBuffer(tmp_path / "b.sqlite")
    ids = []
    for i in range(5):
        ids.append(buf.enqueue(f"t{i}", "tel/a/b/c/d/meas", f'{{"i":{i}}}'))
    pending = buf.pending(limit=10)
    assert len(pending) == 5
    buf.mark_sent(ids[:3])
    assert len(buf.pending(limit=10)) == 2
    stats = buf.stats()
    assert stats["pending"] == 2 and stats["sent"] == 3
    buf.close()


def test_max_rows_evicts_sent_first(tmp_path: Path):
    buf = StoreForwardBuffer(tmp_path / "b.sqlite", max_rows=3)
    a = buf.enqueue("t0", "x", "{}")
    b = buf.enqueue("t1", "x", "{}")
    buf.mark_sent([a, b])
    buf.enqueue("t2", "x", "{}")  # pending
    buf.enqueue("t3", "x", "{}")  # pending -> triggers eviction: oldest sent 'a'
    stats = buf.stats()
    # 'a' evicted, 'b' (sent) remains, 2 pending
    assert stats["sent"] == 1
    assert stats["pending"] == 2
    buf.close()


def test_purge_sent_keeps_last_n(tmp_path: Path):
    buf = StoreForwardBuffer(tmp_path / "b.sqlite")
    ids = [buf.enqueue(f"t{i}", "x", "{}") for i in range(10)]
    buf.mark_sent(ids)
    removed = buf.purge_sent(keep_last_n=3)
    assert removed == 7
    assert buf.stats() == {"pending": 0, "sent": 3}
    buf.close()
