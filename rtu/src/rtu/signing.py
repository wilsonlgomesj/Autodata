"""Ed25519 signing and canonical message bytes.

The signature is computed over a canonical JSON form of the payload with
`sig` and `t_ingest` fields excluded. Both sides (RTU signing, backend
verifying) must produce the same canonical bytes — serialization must be
deterministic.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# Fields removed before computing the signature — must match on both ends.
_EXCLUDED_FROM_SIG = ("sig", "t_ingest")


def canonical_message_bytes(payload: dict[str, Any]) -> bytes:
    """Produce deterministic bytes for signing / verifying.

    Rules:
      - Drop `sig` and `t_ingest`.
      - sort_keys=True at every level.
      - separators without whitespace.
      - ensure_ascii=False so unicode is encoded as UTF-8 bytes directly.
    """
    view = {k: v for k, v in payload.items() if k not in _EXCLUDED_FROM_SIG}
    return json.dumps(
        view,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_payload(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    """Return a `ed25519:<base64>` signature string for the given payload."""
    msg = canonical_message_bytes(payload)
    sig_bytes = private_key.sign(msg)
    return "ed25519:" + base64.b64encode(sig_bytes).decode("ascii")


def verify_signature(payload: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    """Returns True if payload['sig'] verifies against public_key."""
    from cryptography.exceptions import InvalidSignature

    raw = payload.get("sig", "")
    if not isinstance(raw, str) or not raw.startswith("ed25519:"):
        return False
    try:
        sig_bytes = base64.b64decode(raw[len("ed25519:"):])
    except Exception:
        return False
    msg = canonical_message_bytes(payload)
    try:
        public_key.verify(sig_bytes, msg)
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# Key utilities (PEM in/out and random generation for tests/dev)
# ---------------------------------------------------------------------------

def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def load_private_key_pem(path: Path) -> Ed25519PrivateKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path}: not an Ed25519 private key")
    return key


def load_public_key_pem(path: Path) -> Ed25519PublicKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path}: not an Ed25519 public key")
    return key


def public_key_to_pem(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def private_key_to_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
