"""Tests for JWT verification, JWKS cache, and role/MFA dependencies.

We avoid a real Keycloak by generating an RSA keypair on the fly, building a
signed JWT, and feeding the public key into a pre-populated JwksCache.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from api.auth import (  # type: ignore
    AuthConfig,
    AuthContext,
    Authenticator,
    JwksCache,
    bearer_auth,
    require_mfa,
    require_role,
)


ISSUER = "https://iam.example.com/realms/autodata"
AUDIENCE = "autodata-api"


def _generate_rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_public(pub, kid: str) -> dict:
    numbers = pub.public_numbers()
    def _b64u(v: int) -> str:
        import base64
        length = (v.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(v.to_bytes(length, "big")).rstrip(b"=").decode()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u(numbers.n),
        "e": _b64u(numbers.e),
    }


def _sign_token(priv, kid: str, claims: dict) -> str:
    return jwt.encode(
        claims, priv, algorithm="RS256", headers={"kid": kid}
    )


def _authenticator(priv, kid: str):
    pub = priv.public_key()
    cache = JwksCache(jwks_url="http://fake/jwks", _fetcher=lambda url: {"keys": []})
    # Inject the key directly
    cache._keys = {kid: _jwk_from_public(pub, kid)}
    cache._last_fetch = time.monotonic()

    cfg = AuthConfig(jwks_url="http://fake/jwks", issuer=ISSUER, audience=AUDIENCE)
    return Authenticator(cfg, jwks=cache)


def _claims(**over) -> dict:
    now = int(time.time())
    base = {
        "iss": ISSUER, "aud": AUDIENCE,
        "iat": now, "exp": now + 60,
        "sub": "user-123", "email": "op@example.com",
        "realm_access": {"roles": ["operator"]},
        "amr": ["pwd"],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

def test_valid_token_produces_context():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims())
    ctx = auth.verify(token)
    assert ctx.user_id == "user-123"
    assert "operator" in ctx.roles
    assert ctx.mfa is False  # amr=['pwd']


def test_token_with_mfa_claim():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(amr=["pwd", "otp"]))
    assert auth.verify(token).mfa is True


def test_token_with_acr_mfa():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(acr="mfa"))
    assert auth.verify(token).mfa is True


def test_expired_token_rejected():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(
        iat=int(time.time()) - 3600,
        exp=int(time.time()) - 60,
    ))
    with pytest.raises(HTTPException) as exc:
        auth.verify(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_wrong_audience_rejected():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(aud="somebody-else"))
    with pytest.raises(HTTPException):
        auth.verify(token)


def test_wrong_issuer_rejected():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(iss="https://evil.example.com"))
    with pytest.raises(HTTPException):
        auth.verify(token)


def test_unknown_kid_rejected_after_refresh():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "unknown-kid", _claims())
    # Force the refresh path to also return no matching kid.
    auth.jwks._fetcher = lambda url: {"keys": []}
    with pytest.raises(HTTPException) as exc:
        auth.verify(token)
    assert "unknown kid" in exc.value.detail.lower()


def test_resource_access_roles_merged():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(
        realm_access={"roles": ["viewer"]},
        resource_access={"autodata-api": {"roles": ["engineer"]}},
    ))
    ctx = auth.verify(token)
    assert ctx.roles == frozenset(["viewer", "engineer"])


def test_site_scope_claim_parsed():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims(
        site_scope=["mineradora-x-barragem-norte", "mineradora-x-barragem-sul"],
    ))
    ctx = auth.verify(token)
    assert ctx.can_operate_site("mineradora-x-barragem-norte") is True
    assert ctx.can_operate_site("another-site") is False


def test_empty_scope_means_global():
    priv = _generate_rsa()
    auth = _authenticator(priv, "k1")
    token = _sign_token(priv, "k1", _claims())  # no site_scope
    ctx = auth.verify(token)
    assert ctx.can_operate_site("any-site") is True


# ---------------------------------------------------------------------------
# JWKS key rotation
# ---------------------------------------------------------------------------

def test_jwks_refreshes_when_kid_missing():
    priv = _generate_rsa()
    new_kid = "k2"
    # Initial fetch returns nothing; the refresh fetch returns the new key.
    state = {"fetch_count": 0}

    def fetcher(url):
        state["fetch_count"] += 1
        if state["fetch_count"] == 1:
            return {"keys": []}
        return {"keys": [_jwk_from_public(priv.public_key(), new_kid)]}

    cache = JwksCache(jwks_url="http://fake/jwks", _fetcher=fetcher, ttl_s=0)
    cfg = AuthConfig(jwks_url="http://fake/jwks", issuer=ISSUER, audience=AUDIENCE)
    auth = Authenticator(cfg, jwks=cache)
    token = _sign_token(priv, new_kid, _claims())
    ctx = auth.verify(token)
    assert ctx.user_id == "user-123"
    assert state["fetch_count"] >= 2  # original lookup miss → forced refresh


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

class _ReqStub:
    def __init__(self, headers=None):
        class S: pass
        self.state = S()
        self.headers = headers or {}


def test_require_role_raises_without_role():
    req = _ReqStub()
    req.state.auth = AuthContext(
        user_id="x", email=None, roles=frozenset(["viewer"]),
        mfa=True, site_scope=frozenset(), raw_claims={},
    )
    dep = require_role("engineer")
    with pytest.raises(HTTPException) as exc:
        dep(req)
    assert exc.value.status_code == 403


def test_require_role_passes_when_role_present():
    req = _ReqStub()
    req.state.auth = AuthContext(
        user_id="x", email=None, roles=frozenset(["engineer"]),
        mfa=True, site_scope=frozenset(), raw_claims={},
    )
    require_role("engineer")(req)  # does not raise


def test_require_mfa_raises_without_mfa():
    req = _ReqStub()
    req.state.auth = AuthContext(
        user_id="x", email=None, roles=frozenset(),
        mfa=False, site_scope=frozenset(), raw_claims={},
    )
    with pytest.raises(HTTPException) as exc:
        require_mfa()(req)
    assert exc.value.status_code == 403


def test_bearer_auth_dev_bypass_builds_admin_ctx():
    dep = bearer_auth(None, dev_bypass=True)
    req = _ReqStub(headers={})
    ctx = dep(req, None)
    assert ctx.user_id == "dev-user"
    assert "admin" in ctx.roles
    assert ctx.mfa is True
