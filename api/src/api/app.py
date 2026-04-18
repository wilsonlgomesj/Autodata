"""FastAPI app exposing GraphQL + /health.

Auth stub: expects `Authorization: Bearer <token>` in production. In dev
(`AUTH_DISABLED=true`) auth is skipped and the operator is recorded as
`dev-user` in audit rows. In prod, swap `require_auth` for real OIDC JWT
verification and derive `user_id` from the JWT subject.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from strawberry.fastapi import GraphQLRouter

from .db import PgClient
from .repository import Repository
from .schema import schema


def auth_dependency(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Resolves the acting user_id. In dev (AUTH_DISABLED=true) returns
    `dev-user`. In prod, decodes the bearer JWT and returns its subject.
    Stored on request.state for GraphQL context to pick up.
    """
    if os.environ.get("AUTH_DISABLED", "false").lower() == "true":
        user = request.headers.get("X-Dev-User") or "dev-user"
        request.state.user_id = user
        return user
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    # Placeholder — real impl validates JWT against Keycloak JWKS.
    # For now, accept any bearer token and derive the "user" from the
    # X-User header so the audit log at least reflects intent.
    user = request.headers.get("X-User") or "authenticated-user"
    request.state.user_id = user
    return user


def create_app() -> FastAPI:
    dsn = os.environ.get(
        "PG_DSN", "postgresql://autodata:devpassword@localhost:5432/autodata"
    )
    client = PgClient(dsn)
    client.open()

    repo = Repository(client)

    # Optional MQTT publisher for issueCommand mutation. We defer import of
    # paho so tests that only run GraphQL do not need the dependency.
    publisher = None
    mqtt_host = os.environ.get("MQTT_HOST")
    if mqtt_host:
        from .mqtt_publisher import build_publisher
        publisher = build_publisher(
            mqtt_host,
            int(os.environ.get("MQTT_PORT", "1883")),
            client_id=f"api-cmd-{os.getpid()}",
        )

    async def context_getter(request: Request) -> dict:
        user_id = getattr(request.state, "user_id", None) or "unknown"
        return {
            "repo": repo,
            "write": client,
            "publisher": publisher,
            "user_id": user_id,
        }

    graphql_app = GraphQLRouter(
        schema,
        context_getter=context_getter,
        graphiql=os.environ.get("AUTH_DISABLED", "false").lower() == "true",
    )

    app = FastAPI(title="Autodata API", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(
        graphql_app,
        prefix="/graphql",
        dependencies=[Depends(auth_dependency)],
    )
    return app


app = create_app()
