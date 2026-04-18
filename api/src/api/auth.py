"""JWT authentication against a Keycloak-like IdP.

Design:
  - JWKS fetched from the IdP's well-known endpoint, cached with TTL.
  - On request, we pick the `kid` from the JWT header, find the matching
    JWK, convert to PEM, verify signature + iss + aud + exp.
  - Token claims are exposed via AuthContext: user_id, email, roles, mfa.
  - `require_role(role)` and `require_mfa()` return FastAPI dependencies
    suitable for Depends() on sensitive endpoints / mutations.

Pure on the verification path. Network only on JWKS refresh; tests
inject a cached JWKS to avoid real IdP calls.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

@dataclass
class JwksCache:
    jwks_url: str
    ttl_s: int = 600
    _fetcher: Callable[[str], dict] = field(
        default_factory=lambda: _default_jwks_fetcher
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _keys: dict[str, dict] = field(default_factory=dict)
    _last_fetch: float = 0.0

    def get_key(self, kid: str) -> dict | None:
        now = time.monotonic()
        with self._lock:
            stale = (now - self._last_fetch) > self.ttl_s
            if kid in self._keys and not stale:
                return self._keys[kid]
        self._refresh()
        with self._lock:
            return self._keys.get(kid)

    def _refresh(self) -> None:
        data = self._fetcher(self.jwks_url)
        keys = data.get("keys", [])
        with self._lock:
            self._keys = {k["kid"]: k for k in keys if "kid" in k}
            self._last_fetch = time.monotonic()

    def force_refresh(self) -> None:
        self._refresh()


def _default_jwks_fetcher(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Auth context
# ---------------------------------------------------------------------------

@dataclass
class AuthContext:
    user_id: str
    email: str | None
    roles: frozenset[str]
    mfa: bool
    site_scope: frozenset[str]        # sites the user may touch; empty = global
    raw_claims: dict[str, Any]

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def can_operate_site(self, site_id: str) -> bool:
        return not self.site_scope or site_id in self.site_scope


@dataclass
class AuthConfig:
    jwks_url: str
    issuer: str
    audience: str | list[str] = "autodata-api"
    algorithms: tuple[str, ...] = ("RS256",)
    leeway_s: int = 30


class Authenticator:
    def __init__(
        self,
        cfg: AuthConfig,
        jwks: JwksCache | None = None,
    ) -> None:
        self.cfg = cfg
        self.jwks = jwks or JwksCache(jwks_url=cfg.jwks_url)

    def verify(self, token: str) -> AuthContext:
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"invalid token header: {e}")

        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="missing kid in token header")

        jwk = self.jwks.get_key(kid)
        if jwk is None:
            # One forced refresh handles IdP key rotation.
            self.jwks.force_refresh()
            jwk = self.jwks.get_key(kid)
        if jwk is None:
            raise HTTPException(status_code=401, detail=f"unknown kid {kid}")

        pub_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

        try:
            claims = jwt.decode(
                token,
                pub_key,
                algorithms=list(self.cfg.algorithms),
                audience=self.cfg.audience,
                issuer=self.cfg.issuer,
                leeway=self.cfg.leeway_s,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"invalid token: {e}")

        return self._to_context(claims)

    # ------ claim extraction helpers -------------------------------------

    @staticmethod
    def _to_context(claims: dict[str, Any]) -> AuthContext:
        # Keycloak realm roles live at claims['realm_access']['roles']
        realm_roles = (
            claims.get("realm_access", {}).get("roles", []) if claims else []
        )
        # Per-client roles live at resource_access.<client>.roles; we merge all
        resource_roles: list[str] = []
        for client_block in (claims.get("resource_access") or {}).values():
            resource_roles.extend(client_block.get("roles", []))

        all_roles = frozenset([*realm_roles, *resource_roles])

        # Site scope comes from a custom claim `site_scope` (string list).
        site_scope = frozenset(claims.get("site_scope") or [])

        # MFA is signaled either by the `acr` claim being "mfa" or by the
        # OIDC-standard `amr` array containing one of "mfa", "otp", "hwk".
        mfa_amr = set(claims.get("amr") or [])
        mfa = (claims.get("acr") == "mfa") or bool(
            mfa_amr & {"mfa", "otp", "hwk", "totp"}
        )

        return AuthContext(
            user_id=claims.get("sub") or "unknown",
            email=claims.get("email"),
            roles=all_roles,
            mfa=mfa,
            site_scope=site_scope,
            raw_claims=claims,
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def bearer_auth(authenticator: Authenticator, dev_bypass: bool = False):
    """Build a FastAPI dependency that verifies Bearer tokens.

    dev_bypass=True (AUTH_DISABLED=true env) returns a fake admin context
    without touching the IdP. The dev context is explicitly flagged so
    require_role and require_mfa still apply correctly in dev.
    """

    def dep(request: Request, authorization: Optional[str] = Header(default=None)) -> AuthContext:
        if dev_bypass:
            ctx = AuthContext(
                user_id=request.headers.get("X-Dev-User") or "dev-user",
                email=None,
                roles=frozenset(
                    request.headers.get("X-Dev-Roles", "admin,engineer,operator").split(",")
                ),
                mfa=request.headers.get("X-Dev-Mfa", "true").lower() == "true",
                site_scope=frozenset(),  # global
                raw_claims={},
            )
            request.state.auth = ctx
            return ctx

        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        ctx = authenticator.verify(token)
        request.state.auth = ctx
        return ctx

    return dep


def require_role(role: str):
    """Dependency factory — composes on top of bearer_auth via request.state."""

    def dep(request: Request) -> None:
        ctx: AuthContext | None = getattr(request.state, "auth", None)
        if ctx is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if not ctx.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"role {role!r} required; have {sorted(ctx.roles)}",
            )

    return dep


def require_mfa():
    """Dependency that enforces the token carries an MFA claim."""

    def dep(request: Request) -> None:
        ctx: AuthContext | None = getattr(request.state, "auth", None)
        if ctx is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if not ctx.mfa:
            raise HTTPException(
                status_code=403,
                detail="MFA required for this operation",
            )

    return dep
