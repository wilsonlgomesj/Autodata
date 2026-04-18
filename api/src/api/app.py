"""FastAPI app exposing GraphQL + /health.

Auth stub: expects `Authorization: Bearer <token>` in production. Skipped in
dev for easy exploration via the GraphiQL UI.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from strawberry.fastapi import GraphQLRouter

from .db import PgClient
from .repository import Repository
from .schema import schema


def require_auth(authorization: str | None = Header(default=None)) -> None:
    # Dev bypass if AUTH_DISABLED=true (compose.dev). In prod, swap for real
    # OIDC introspection via Keycloak.
    if os.environ.get("AUTH_DISABLED", "false").lower() == "true":
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    # Placeholder — real impl validates JWT against Keycloak JWKS.


def create_app() -> FastAPI:
    dsn = os.environ.get(
        "PG_DSN", "postgresql://autodata:devpassword@localhost:5432/autodata"
    )
    client = PgClient(dsn)
    client.open()

    repo = Repository(client)

    async def context_getter() -> dict:
        return {"repo": repo}

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
        dependencies=[Depends(require_auth)],
    )
    return app


app = create_app()
