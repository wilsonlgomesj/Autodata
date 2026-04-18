"""Tests for the Repository layer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.repository import Repository  # type: ignore

from .fakes import FakeDatabaseClient


def _client_with_sites():
    client = FakeDatabaseClient()
    client.on(
        "FROM geo.site",
        lambda params: [
            ("mineradora-x-barragem-norte", "Barragem X", "BR",
             "America/Sao_Paulo", -19.9, -43.9),
        ],
    )
    return client


def test_list_sites():
    repo = Repository(_client_with_sites())
    sites = repo.list_sites()
    assert len(sites) == 1
    assert sites[0].site_id == "mineradora-x-barragem-norte"


def test_get_site_found():
    repo = Repository(_client_with_sites())
    site = repo.get_site("mineradora-x-barragem-norte")
    assert site is not None
    assert site.display_name == "Barragem X"


def test_get_site_missing():
    client = FakeDatabaseClient()
    client.on("FROM geo.site", lambda params: [])
    repo = Repository(client)
    assert repo.get_site("nope") is None


def test_list_sensors_filters_passed_through():
    client = FakeDatabaseClient()
    captured: dict = {}

    def _respond(params):
        captured["params"] = params
        return [
            (
                "mineradora-x-barragem-norte", "pz-sec02-fund-01",
                "piezometer_vw", "barragem-principal", "sec-02-centro",
                "rtu-bx-c1", "PZ S2", datetime(2024, 6, 11, tzinfo=timezone.utc),
                True,
            ),
        ]

    client.on("FROM geo.sensor", _respond)
    repo = Repository(client)
    sensors = repo.list_sensors(
        "mineradora-x-barragem-norte",
        structure_id="barragem-principal",
        sensor_type="piezometer_vw",
    )
    assert len(sensors) == 1
    # Params shape matches SENSORS_SQL: (site, struct, struct, type, type)
    assert captured["params"][0] == "mineradora-x-barragem-norte"
    assert captured["params"][1] == "barragem-principal"
    assert captured["params"][3] == "piezometer_vw"


def test_timeseries_rejects_unknown_resolution():
    repo = Repository(FakeDatabaseClient())
    with pytest.raises(ValueError):
        repo.timeseries(
            "s", "sensor", "pressure_kpa",
            datetime.now(timezone.utc), datetime.now(timezone.utc),
            resolution="7d",
        )


def test_timeseries_picks_correct_sql_per_resolution():
    client = FakeDatabaseClient()
    client.on("FROM geo.measurement\n", lambda p: [])  # raw
    client.on("FROM geo.measurement_1min", lambda p: [])
    client.on("FROM geo.measurement_1h", lambda p: [])

    repo = Repository(client)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 2, tzinfo=timezone.utc)

    repo.timeseries("s", "sensor", "m", t0, t1, resolution="raw")
    repo.timeseries("s", "sensor", "m", t0, t1, resolution="1min")
    repo.timeseries("s", "sensor", "m", t0, t1, resolution="1h")

    sqls = [call[0] for call in client.calls]
    assert any("geo.measurement\n" in s for s in sqls)
    assert any("geo.measurement_1min" in s for s in sqls)
    assert any("geo.measurement_1h" in s for s in sqls)


def test_list_alerts_passes_level_and_since():
    client = FakeDatabaseClient()
    seen: dict = {}

    def _respond(params):
        seen["params"] = params
        return []

    client.on("FROM geo.alert_event", _respond)
    repo = Repository(client)
    repo.list_alerts(
        "s", level="ALERTA",
        since=datetime(2026, 1, 1, tzinfo=timezone.utc), limit=50
    )
    # (site, level, level, since, since, limit)
    assert seen["params"][1] == "ALERTA"
    assert seen["params"][2] == "ALERTA"
    assert seen["params"][-1] == 50
