"""GraphQL schema tests — exercise resolvers with a fake repo via execute()."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from api.repository import Repository  # type: ignore
from api.schema import schema  # type: ignore

from .fakes import FakeDatabaseClient


def _execute(query: str, variables: dict | None = None, repo: Repository | None = None):
    return asyncio.run(
        schema.execute(
            query,
            variable_values=variables or {},
            context_value={"repo": repo},
        )
    )


def test_sites_query():
    client = FakeDatabaseClient()
    client.on(
        "FROM geo.site",
        lambda p: [("mineradora-x-barragem-norte", "Barragem X", "BR",
                    "America/Sao_Paulo", -19.9, -43.9)],
    )
    repo = Repository(client)
    result = _execute(
        "query { sites { siteId displayName country } }", repo=repo
    )
    assert result.errors is None, result.errors
    assert result.data["sites"] == [
        {
            "siteId": "mineradora-x-barragem-norte",
            "displayName": "Barragem X",
            "country": "BR",
        }
    ]


def test_site_query_returns_null_when_missing():
    client = FakeDatabaseClient()
    client.on("FROM geo.site", lambda p: [])
    repo = Repository(client)
    result = _execute(
        'query { site(siteId: "nope") { siteId } }', repo=repo
    )
    assert result.errors is None
    assert result.data["site"] is None


def test_latest_measurements_query():
    client = FakeDatabaseClient()
    t = datetime(2026, 4, 18, 13, 45, tzinfo=timezone.utc)
    client.on(
        "FROM geo.measurement",
        lambda p: [
            ("mineradora-x-barragem-norte", "pz-sec02-fund-01",
             "pressure_kpa", t, 312.4, "GOOD", []),
            ("mineradora-x-barragem-norte", "pz-sec02-fund-01",
             "temp_c", t, 25.6, "GOOD", []),
        ],
    )
    repo = Repository(client)
    q = """
      query($site: String!, $sensor: String!) {
        latestMeasurements(siteId: $site, sensorId: $sensor) {
          metric value quality
        }
      }
    """
    result = _execute(q, {"site": "mineradora-x-barragem-norte",
                           "sensor": "pz-sec02-fund-01"}, repo=repo)
    assert result.errors is None, result.errors
    metrics = {m["metric"] for m in result.data["latestMeasurements"]}
    assert metrics == {"pressure_kpa", "temp_c"}


def test_alerts_query_serializes_event_id():
    client = FakeDatabaseClient()
    client.on(
        "FROM geo.alert_event",
        lambda p: [
            (
                UUID("12345678-1234-5678-1234-567812345678"),
                "mineradora-x-barragem-norte",
                "barragem-principal",
                "pz-fund-alerta",
                "v1.0.0",
                "ALERTA",
                datetime(2026, 4, 18, 14, 10, tzinfo=timezone.utc),
                None,
                ["pz-sec02-fund-01"],
            )
        ],
    )
    repo = Repository(client)
    q = """
      query($site: String!) {
        alerts(siteId: $site, limit: 10) {
          eventId ruleId level sensors
        }
      }
    """
    result = _execute(q, {"site": "mineradora-x-barragem-norte"}, repo=repo)
    assert result.errors is None, result.errors
    alert = result.data["alerts"][0]
    assert alert["eventId"] == "12345678-1234-5678-1234-567812345678"
    assert alert["level"] == "ALERTA"
    assert alert["sensors"] == ["pz-sec02-fund-01"]


def test_timeseries_query_with_resolution():
    client = FakeDatabaseClient()
    t = datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc)
    client.on(
        "FROM geo.measurement_1min",
        lambda p: [(t, 12, 310.0, 314.0, 312.0)],
    )
    repo = Repository(client)
    q = """
      query($site: String!, $sensor: String!, $metric: String!,
            $tFrom: DateTime!, $tTo: DateTime!) {
        timeseries(
          siteId: $site, sensorId: $sensor, metric: $metric,
          tFrom: $tFrom, tTo: $tTo, resolution: "1min"
        ) { n vMin vMax vAvg }
      }
    """
    result = _execute(
        q,
        {
            "site": "mineradora-x-barragem-norte",
            "sensor": "pz-sec02-fund-01",
            "metric": "pressure_kpa",
            "tFrom": "2026-04-18T00:00:00Z",
            "tTo": "2026-04-19T00:00:00Z",
        },
        repo=repo,
    )
    assert result.errors is None, result.errors
    assert result.data["timeseries"][0] == {
        "n": 12, "vMin": 310.0, "vMax": 314.0, "vAvg": 312.0,
    }
