"""GraphQL schema built with Strawberry.

Read-only surface. Mutations (e.g., acknowledge alert) will come later as a
separate file to keep authZ concerns isolated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import strawberry
from strawberry.types import Info

from .repository import Repository


# ---------------------------------------------------------------------------
# GraphQL types
# ---------------------------------------------------------------------------

@strawberry.type
class Site:
    site_id: str
    display_name: str
    country: str
    timezone: str
    lat: Optional[float]
    lon: Optional[float]


@strawberry.type
class Structure:
    site_id: str
    structure_id: str
    kind: str
    display_name: str
    height_m: Optional[float]
    crest_length_m: Optional[float]
    risk_class: Optional[str]


@strawberry.type
class Sensor:
    site_id: str
    sensor_id: str
    sensor_type: str
    structure_id: str
    section_id: str
    device_id: str
    display_name: str
    installed_on: Optional[datetime]
    active: bool


@strawberry.type
class LatestMeasurement:
    site_id: str
    sensor_id: str
    metric: str
    t_sample: datetime
    value: Optional[float]
    quality: str
    flags: list[str]


@strawberry.type
class TimeseriesPoint:
    bucket: datetime
    n: int
    v_min: Optional[float]
    v_max: Optional[float]
    v_avg: Optional[float]


@strawberry.type
class AlertSummary:
    event_id: str
    site_id: str
    structure_id: Optional[str]
    rule_id: str
    rule_version: str
    level: str
    t_triggered: datetime
    t_resolved: Optional[datetime]
    sensors: list[str]


# ---------------------------------------------------------------------------
# Query root — uses info.context["repo"] as the injection point.
# ---------------------------------------------------------------------------

def _repo(info: Info) -> Repository:
    return info.context["repo"]


@strawberry.type
class Query:
    @strawberry.field
    def sites(self, info: Info) -> list[Site]:
        return [Site(**s.__dict__) for s in _repo(info).list_sites()]

    @strawberry.field
    def site(self, info: Info, site_id: str) -> Optional[Site]:
        s = _repo(info).get_site(site_id)
        return Site(**s.__dict__) if s else None

    @strawberry.field
    def structures(self, info: Info, site_id: str) -> list[Structure]:
        return [
            Structure(**s.__dict__)
            for s in _repo(info).list_structures(site_id)
        ]

    @strawberry.field
    def sensors(
        self,
        info: Info,
        site_id: str,
        structure_id: Optional[str] = None,
        sensor_type: Optional[str] = None,
    ) -> list[Sensor]:
        return [
            Sensor(**s.__dict__)
            for s in _repo(info).list_sensors(site_id, structure_id, sensor_type)
        ]

    @strawberry.field
    def latest_measurements(
        self, info: Info, site_id: str, sensor_id: str
    ) -> list[LatestMeasurement]:
        return [
            LatestMeasurement(**m.__dict__)
            for m in _repo(info).latest_measurements(site_id, sensor_id)
        ]

    @strawberry.field
    def timeseries(
        self,
        info: Info,
        site_id: str,
        sensor_id: str,
        metric: str,
        t_from: datetime,
        t_to: datetime,
        resolution: str = "raw",
        limit: int = 10000,
    ) -> list[TimeseriesPoint]:
        return [
            TimeseriesPoint(**p.__dict__)
            for p in _repo(info).timeseries(
                site_id, sensor_id, metric, t_from, t_to, resolution, limit
            )
        ]

    @strawberry.field
    def alerts(
        self,
        info: Info,
        site_id: str,
        level: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AlertSummary]:
        out: list[AlertSummary] = []
        for a in _repo(info).list_alerts(site_id, level, since, limit):
            d = a.__dict__.copy()
            # event_id arrives from psycopg as UUID; serialize to str
            d["event_id"] = str(d["event_id"])
            out.append(AlertSummary(**d))
        return out


schema = strawberry.Schema(query=Query)
