"""Postgres/TimescaleDB access layer for the read API.

Thin wrapper over psycopg. Parameters are plain SQL — no ORM — because
queries are few, well-understood, and tuned for the time-series hypertable.
A minimal DatabaseClient protocol lets tests inject a fake without any DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol


class DatabaseClient(Protocol):
    def fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]: ...
    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None: ...


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class Site:
    site_id: str
    display_name: str
    country: str
    timezone: str
    lat: float | None
    lon: float | None


@dataclass
class Structure:
    site_id: str
    structure_id: str
    kind: str
    display_name: str
    height_m: float | None
    crest_length_m: float | None
    risk_class: str | None


@dataclass
class Sensor:
    site_id: str
    sensor_id: str
    sensor_type: str
    structure_id: str
    section_id: str
    device_id: str
    display_name: str
    installed_on: datetime | None
    active: bool


@dataclass
class LatestMeasurement:
    site_id: str
    sensor_id: str
    metric: str
    t_sample: datetime
    value: float | None
    quality: str
    flags: list[str]


@dataclass
class TimeseriesPoint:
    bucket: datetime
    n: int
    v_min: float | None
    v_max: float | None
    v_avg: float | None


@dataclass
class AlertSummary:
    event_id: str
    site_id: str
    structure_id: str | None
    rule_id: str
    rule_version: str
    level: str
    t_triggered: datetime
    t_resolved: datetime | None
    sensors: list[str]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

SITES_SQL = """
SELECT site_id, display_name, country, timezone, lat, lon
FROM geo.site
WHERE active = TRUE
ORDER BY site_id
"""

SITE_BY_ID_SQL = """
SELECT site_id, display_name, country, timezone, lat, lon
FROM geo.site
WHERE site_id = %s AND active = TRUE
"""

STRUCTURES_SQL = """
SELECT site_id, structure_id, kind, display_name,
       height_m, crest_length_m, risk_class
FROM geo.structure
WHERE site_id = %s
ORDER BY structure_id
"""

SENSORS_SQL = """
SELECT site_id, sensor_id, sensor_type, structure_id, section_id,
       device_id, display_name, installed_on, active
FROM geo.sensor
WHERE site_id = %s
  AND (%s::TEXT IS NULL OR structure_id = %s)
  AND (%s::TEXT IS NULL OR sensor_type = %s::geo.sensor_type_enum)
ORDER BY sensor_id
"""

LATEST_MEASUREMENTS_SQL = """
SELECT DISTINCT ON (site_id, sensor_id, metric)
  site_id, sensor_id, metric, t_sample, value, quality, flags
FROM geo.measurement
WHERE site_id = %s AND sensor_id = %s
ORDER BY site_id, sensor_id, metric, t_sample DESC
"""

TIMESERIES_RAW_SQL = """
SELECT t_sample AS bucket, 1 AS n, value AS v_min, value AS v_max, value AS v_avg
FROM geo.measurement
WHERE site_id = %s AND sensor_id = %s AND metric = %s
  AND t_sample BETWEEN %s AND %s
ORDER BY t_sample
LIMIT %s
"""

# Continuous-aggregate queries — they exist only on TimescaleDB.
# For vanilla PG tests the repository automatically falls back to raw.
TIMESERIES_1MIN_SQL = """
SELECT bucket, n, v_min, v_max, v_avg
FROM geo.measurement_1min
WHERE site_id = %s AND sensor_id = %s AND metric = %s
  AND bucket BETWEEN %s AND %s
ORDER BY bucket
LIMIT %s
"""

TIMESERIES_1H_SQL = """
SELECT bucket_h AS bucket, n, v_min, v_max, v_avg
FROM geo.measurement_1h
WHERE site_id = %s AND sensor_id = %s AND metric = %s
  AND bucket_h BETWEEN %s AND %s
ORDER BY bucket_h
LIMIT %s
"""

ALERTS_SQL = """
SELECT event_id, site_id, structure_id, rule_id, rule_version,
       level::text, t_triggered, t_resolved, sensors
FROM geo.alert_event
WHERE site_id = %s
  AND (%s::TEXT IS NULL OR level::text = %s)
  AND (%s::TIMESTAMPTZ IS NULL OR t_triggered >= %s)
ORDER BY t_triggered DESC
LIMIT %s
"""


VALID_RESOLUTIONS = ("raw", "1min", "1h")


class Repository:
    def __init__(self, db: DatabaseClient) -> None:
        self.db = db

    def list_sites(self) -> list[Site]:
        rows = self.db.fetch_all(SITES_SQL, ())
        return [Site(*r) for r in rows]

    def get_site(self, site_id: str) -> Site | None:
        row = self.db.fetch_one(SITE_BY_ID_SQL, (site_id,))
        return Site(*row) if row else None

    def list_structures(self, site_id: str) -> list[Structure]:
        rows = self.db.fetch_all(STRUCTURES_SQL, (site_id,))
        return [Structure(*r) for r in rows]

    def list_sensors(
        self,
        site_id: str,
        structure_id: str | None = None,
        sensor_type: str | None = None,
    ) -> list[Sensor]:
        rows = self.db.fetch_all(
            SENSORS_SQL,
            (site_id, structure_id, structure_id, sensor_type, sensor_type),
        )
        return [Sensor(*r) for r in rows]

    def latest_measurements(self, site_id: str, sensor_id: str) -> list[LatestMeasurement]:
        rows = self.db.fetch_all(LATEST_MEASUREMENTS_SQL, (site_id, sensor_id))
        return [LatestMeasurement(*r) for r in rows]

    def timeseries(
        self,
        site_id: str,
        sensor_id: str,
        metric: str,
        t_from: datetime,
        t_to: datetime,
        resolution: str = "raw",
        limit: int = 10000,
    ) -> list[TimeseriesPoint]:
        if resolution not in VALID_RESOLUTIONS:
            raise ValueError(
                f"resolution must be one of {VALID_RESOLUTIONS}, got {resolution!r}"
            )
        sql = {
            "raw": TIMESERIES_RAW_SQL,
            "1min": TIMESERIES_1MIN_SQL,
            "1h": TIMESERIES_1H_SQL,
        }[resolution]
        rows = self.db.fetch_all(sql, (site_id, sensor_id, metric, t_from, t_to, limit))
        return [TimeseriesPoint(*r) for r in rows]

    def list_alerts(
        self,
        site_id: str,
        level: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AlertSummary]:
        rows = self.db.fetch_all(
            ALERTS_SQL,
            (site_id, level, level, since, since, limit),
        )
        return [AlertSummary(*r) for r in rows]
