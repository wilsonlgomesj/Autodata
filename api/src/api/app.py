"""FastAPI app wiring GraphQL (Strawberry) with Keycloak-backed auth.

In dev (AUTH_DISABLED=true) auth is bypassed and the GraphQL context is
populated with an admin-ish AuthContext whose mfa=true so all MFA-gated
mutations still function through GraphiQL.

In prod, every GraphQL request must carry a Bearer token; the verifier pulls
JWKs from `KEYCLOAK_JWKS_URL`, verifies issuer/audience/exp, and exposes
the resulting AuthContext to mutation resolvers via context["auth"].
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from .auth import (
    AuthConfig,
    AuthContext,
    Authenticator,
    JwksCache,
    bearer_auth,
)
from .db import PgClient
from .repository import Repository
from .schema import schema


def _build_authenticator() -> Optional[Authenticator]:
    jwks_url = os.environ.get("KEYCLOAK_JWKS_URL")
    issuer = os.environ.get("KEYCLOAK_ISSUER")
    audience = os.environ.get("KEYCLOAK_AUDIENCE", "autodata-api")
    if not jwks_url or not issuer:
        return None
    cfg = AuthConfig(
        jwks_url=jwks_url,
        issuer=issuer,
        audience=audience,
    )
    return Authenticator(cfg)


def create_app() -> FastAPI:
    dsn = os.environ.get(
        "PG_DSN", "postgresql://autodata:devpassword@localhost:5432/autodata"
    )
    client = PgClient(dsn)
    client.open()

    repo = Repository(client)

    publisher = None
    mqtt_host = os.environ.get("MQTT_HOST")
    if mqtt_host:
        from .mqtt_publisher import build_publisher
        publisher = build_publisher(
            mqtt_host,
            int(os.environ.get("MQTT_PORT", "1883")),
            client_id=f"api-cmd-{os.getpid()}",
        )

    dev_bypass = os.environ.get("AUTH_DISABLED", "false").lower() == "true"
    authenticator = _build_authenticator()

    if not dev_bypass and authenticator is None:
        raise RuntimeError(
            "KEYCLOAK_JWKS_URL and KEYCLOAK_ISSUER must be set unless "
            "AUTH_DISABLED=true"
        )

    auth_dep = bearer_auth(authenticator, dev_bypass=dev_bypass)

    async def context_getter(request: Request) -> dict:
        ctx: AuthContext | None = getattr(request.state, "auth", None)
        return {
            "repo": repo,
            "write": client,
            "publisher": publisher,
            "user_id": ctx.user_id if ctx else "unknown",
            "auth": ctx,
        }

    graphql_app = GraphQLRouter(
        schema,
        context_getter=context_getter,
        graphiql=dev_bypass,
    )

    app = FastAPI(title="Autodata API", version="0.1.0")

    # CORS for the SPA. Allowed origins come from CORS_ORIGINS
    # (comma-separated) or default to the dev frontend on :5173 / :8082.
    origins = [
        o.strip() for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:8082,http://127.0.0.1:5173",
        ).split(",") if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Dev-User",
                        "X-Dev-Roles", "X-Dev-Mfa", "X-User"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # --- GeoJSON REST -----------------------------------------------------
    # GraphQL is great for the dashboard, but Leaflet/Mapbox/OpenLayers
    # consume GeoJSON via plain HTTP. Mirror the spatial queries at simple
    # REST paths for drop-in map layers.

    @app.get("/gis/{site_id}/sensors.geojson")
    def gis_sensors(site_id: str, _=Depends(auth_dep)) -> dict:
        return repo.sensors_geojson(site_id)

    @app.get("/gis/{site_id}/structures.geojson")
    def gis_structures(site_id: str, _=Depends(auth_dep)) -> dict:
        return repo.structures_geojson(site_id)

    @app.get("/gis/{site_id}/site.geojson")
    def gis_site(site_id: str, _=Depends(auth_dep)) -> dict:
        data = repo.site_boundary(site_id)
        if data is None:
            raise HTTPException(status_code=404, detail="site has no geometry")
        return data

    @app.get("/authz-ping")
    def authz_ping(ctx: AuthContext = Depends(auth_dep)) -> dict:
        """Sanity endpoint for debugging auth: echoes parsed claims."""
        return {
            "user_id": ctx.user_id,
            "email": ctx.email,
            "roles": sorted(ctx.roles),
            "mfa": ctx.mfa,
            "site_scope": sorted(ctx.site_scope),
        }

    app.include_router(
        graphql_app,
        prefix="/graphql",
        dependencies=[Depends(auth_dep)],
    )
    return app


app = create_app()
