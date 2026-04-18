"""Load thresholds from the `geo.threshold` table.

Returns a callable suitable for RuleEvaluator.thresholds_for. The callable
is cached per (sensor, metric) and refreshed on TTL or on explicit reload.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import psycopg
from psycopg_pool import ConnectionPool


THRESHOLD_QUERY = """
SELECT atencao, alerta, emergencia_n1, emergencia_n2
FROM geo.threshold
WHERE site_id = %s AND sensor_id = %s AND metric = %s
  AND effective_to IS NULL
LIMIT 1
"""


@dataclass
class ThresholdCache:
    pool: ConnectionPool
    ttl_s: int = 60
    _cache: dict[tuple[str, str, str], tuple[float, dict[str, float]]] = None  # type: ignore

    def __post_init__(self):
        if self._cache is None:
            self._cache = {}

    def get(self, site_id: str, sensor_id: str, metric: str) -> dict[str, float]:
        key = (site_id, sensor_id, metric)
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self.ttl_s:
            return hit[1]

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(THRESHOLD_QUERY, (site_id, sensor_id, metric))
                row = cur.fetchone()

        result: dict[str, float] = {}
        if row:
            keys = ("atencao", "alerta", "emergencia_n1", "emergencia_n2")
            for k, v in zip(keys, row):
                if v is not None:
                    result[k] = float(v)
        self._cache[key] = (now, result)
        return result

    def invalidate(self) -> None:
        self._cache.clear()

    def as_callable(self, site_id: str) -> Callable:
        def _cb(rule, sensor_id: str) -> dict[str, float]:
            return self.get(site_id, sensor_id, rule.metric)
        return _cb
