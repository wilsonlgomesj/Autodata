"""Tests for GIS repository methods and GraphQL resolvers."""

from __future__ import annotations

import asyncio

from api.auth import AuthContext  # type: ignore
from api.repository import Repository  # type: ignore
from api.schema import schema  # type: ignore

from .fakes import FakeDatabaseClient


def _execute(query, variables=None, repo=None):
    context = {
        "repo": repo, "write": None, "publisher": None,
        "user_id": "x",
        "auth": AuthContext(
            user_id="x", email=None, roles=frozenset(["viewer"]),
            mfa=True, site_scope=frozenset(), raw_claims={},
        ),
    }
    return asyncio.run(
        schema.execute(query, variable_values=variables or {},
                        context_value=context)
    )


def test_repository_sensors_geojson_returns_featurecollection():
    client = FakeDatabaseClient()
    client.on(
        "FROM geo.sensor_feature",
        lambda p: [(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "pz-sec02-fund-01",
                        "geometry": {"type": "Point", "coordinates": [-43.9, -19.9]},
                        "properties": {"sensor_id": "pz-sec02-fund-01"},
                    }
                ],
            },
        )],
    )
    repo = Repository(client)
    fc = repo.sensors_geojson("site-x")
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["type"] == "Point"


def test_repository_site_boundary_handles_null_geometries():
    client = FakeDatabaseClient()
    client.on("FROM geo.site", lambda p: [(None, None)])
    repo = Repository(client)
    assert repo.site_boundary("site-x") is None


def test_graphql_sensors_geojson_resolver():
    client = FakeDatabaseClient()
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "pz-a", "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"sensor_id": "pz-a"},
            }
        ],
    }
    client.on("FROM geo.sensor_feature", lambda p: [(fc,)])
    repo = Repository(client)
    q = 'query($s: String!) { sensorsGeojson(siteId: $s) }'
    r = _execute(q, {"s": "site-x"}, repo=repo)
    assert r.errors is None, r.errors
    assert r.data["sensorsGeojson"]["type"] == "FeatureCollection"


def test_structures_geojson_empty_site_returns_empty_collection():
    client = FakeDatabaseClient()
    client.on(
        "FROM geo.structure",
        lambda p: [({"type": "FeatureCollection", "features": []},)],
    )
    repo = Repository(client)
    fc = repo.structures_geojson("site-empty")
    assert fc == {"type": "FeatureCollection", "features": []}
