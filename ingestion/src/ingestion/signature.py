"""Ed25519 signature verification for incoming telemetry payloads.

The canonical-bytes algorithm must match rtu/src/rtu/signing.py exactly,
otherwise valid messages will be rejected. We keep the two implementations
intentionally separated (backend never imports RTU code) but the test suite
exercises round-trip sign→verify against payloads built from both sides.
"""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any, Callable, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_EXCLUDED_FROM_SIG = ("sig", "t_ingest")


def canonical_message_bytes(payload: dict[str, Any]) -> bytes:
    view = {k: v for k, v in payload.items() if k not in _EXCLUDED_FROM_SIG}
    return json.dumps(
        view,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class PublicKeyResolver(Protocol):
    """Given (site_id, device_id), return the Ed25519 public key or None."""

    def __call__(self, site_id: str, device_id: str) -> Ed25519PublicKey | None: ...


def verify_payload(payload: dict[str, Any], resolver: PublicKeyResolver) -> bool:
    """Verify the payload's `sig`. Returns True only on valid signature."""
    site = payload.get("site")
    device = payload.get("device")
    if not isinstance(site, str) or not isinstance(device, str):
        return False

    key = resolver(site, device)
    if key is None:
        return False

    raw = payload.get("sig", "")
    if not isinstance(raw, str) or not raw.startswith("ed25519:"):
        return False
    try:
        sig_bytes = base64.b64decode(raw[len("ed25519:"):])
    except Exception:
        return False

    try:
        key.verify(sig_bytes, canonical_message_bytes(payload))
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# Postgres-backed resolver with TTL cache
# ---------------------------------------------------------------------------

PUBLIC_KEY_QUERY = """
SELECT public_key FROM geo.device
WHERE site_id = %s AND device_id = %s
LIMIT 1
"""


class PgPublicKeyResolver:
    """Loads PEM public keys from geo.device. Caches in-memory with a TTL.

    public_key column stores PEM text. Base64-only keys are also accepted
    and wrapped into a PEM SubjectPublicKeyInfo block.
    """

    def __init__(self, pool, ttl_s: int = 300) -> None:
        self.pool = pool
        self.ttl_s = ttl_s
        self._cache: dict[tuple[str, str], tuple[float, Ed25519PublicKey | None]] = {}
        self._lock = threading.Lock()

    def _load(self, site: str, device: str) -> Ed25519PublicKey | None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(PUBLIC_KEY_QUERY, (site, device))
                row = cur.fetchone()
        if not row or not row[0]:
            return None
        pem_or_b64 = row[0]
        if "BEGIN PUBLIC KEY" not in pem_or_b64:
            return None
        try:
            key = serialization.load_pem_public_key(pem_or_b64.encode("utf-8"))
        except Exception:
            return None
        if not isinstance(key, Ed25519PublicKey):
            return None
        return key

    def __call__(self, site: str, device: str) -> Ed25519PublicKey | None:
        import time
        key = (site, device)
        with self._lock:
            hit = self._cache.get(key)
            if hit and (time.monotonic() - hit[0]) < self.ttl_s:
                return hit[1]
        loaded = self._load(site, device)
        with self._lock:
            self._cache[key] = (time.monotonic(), loaded)
        return loaded
