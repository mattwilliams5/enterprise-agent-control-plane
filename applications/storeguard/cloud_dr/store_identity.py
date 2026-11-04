"""StoreGuard store-client authentication primitives (independent of agent SG-IDENTITY-001).

Protocol v1: Ed25519 signs exact body bytes and bound HTTP metadata. Public keys are
registered through a trusted enrollment step, NOT by a request from the store itself.
This module deliberately does not alter the existing FastAPI route or deploy services.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable
import base64
import re
import secrets
import sqlite3
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


class StoreAuthenticationError(Exception):
    """Authentication failed; caller should receive a generic 401."""


_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
_REQUIRED = ("X-Store-ID", "X-Store-Key-ID", "X-Store-Timestamp", "X-Store-Nonce", "X-Store-Signature")


def _validate_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_b64url(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise StoreAuthenticationError("Invalid store credentials")
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise StoreAuthenticationError("Invalid store credentials") from None


def signature_message(*, store_id: str, key_id: str, timestamp: int, nonce: str,
                      method: str, path: str, body: bytes) -> bytes:
    """Unambiguous fixed-order protocol v1; sign raw HTTP bytes (no JSON normalization)."""
    _validate_id(store_id, "store_id")
    _validate_id(key_id, "key_id")
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise ValueError("Invalid nonce")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
        raise ValueError("Invalid timestamp")
    if method != "POST" or path != "/orders":
        raise ValueError("Only POST /orders is supported by protocol v1")
    if not isinstance(body, bytes):
        raise ValueError("Body must be raw bytes")
    return (f"SG-STORE-V1\n{store_id}\n{key_id}\n{timestamp}\n{nonce}\n"
            f"POST\n/orders\n{sha256(body).hexdigest()}\n").encode("ascii")


def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def private_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())


def sign_order_request(private_key: Ed25519PrivateKey, *, store_id: str, key_id: str,
                       body: bytes, timestamp: int | None = None,
                       nonce: str | None = None) -> dict[str, str]:
    """Client helper; generate a fresh nonce per HTTP attempt, retain order idempotency key."""
    if timestamp is None:
        timestamp = int(time.time())
    if nonce is None:
        nonce = secrets.token_urlsafe(24)
    message = signature_message(store_id=store_id, key_id=key_id,
        timestamp=timestamp, nonce=nonce, method="POST", path="/orders", body=body)
    return {"X-Store-ID": store_id, "X-Store-Key-ID": key_id,
            "X-Store-Timestamp": str(timestamp), "X-Store-Nonce": nonce,
            "X-Store-Signature": _b64url(private_key.sign(message))}


@dataclass(frozen=True)
class VerifiedStore:
    store_id: str
    key_id: str
    nonce: str
    timestamp: int


class StoreIdentityRegistry:
    """SQLite demonstration verifier registry. Do not expose enrollment over HTTP."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS store_public_keys (
           store_id TEXT NOT NULL, key_id TEXT NOT NULL, public_key BLOB NOT NULL,
           revoked INTEGER NOT NULL DEFAULT 0,
           PRIMARY KEY (store_id, key_id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS store_replay_nonces (
           store_id TEXT NOT NULL, key_id TEXT NOT NULL, nonce TEXT NOT NULL,
           expires_at INTEGER NOT NULL,
           PRIMARY KEY (store_id, key_id, nonce))""")

    def enroll(self, store_id: str, key_id: str, public_key: bytes):
        _validate_id(store_id, "store_id")
        _validate_id(key_id, "key_id")
        if not isinstance(public_key, bytes) or len(public_key) != 32:
            raise ValueError("Expected 32-byte Ed25519 public key")
        Ed25519PublicKey.from_public_bytes(public_key)
        # No replacement or unrevocation through enrollment. Rotate using a new key ID.
        self.db.execute("INSERT INTO store_public_keys (store_id,key_id,public_key) VALUES (?,?,?)",
                        (store_id, key_id, public_key))

    def revoke(self, store_id: str, key_id: str):
        cur = self.db.execute("UPDATE store_public_keys SET revoked=1 WHERE store_id=? AND key_id=?",
                              (store_id, key_id))
        if cur.rowcount != 1:
            raise ValueError("Unknown key")

    def verify(self, *, headers: dict[str, str], method: str, path: str,
               body: bytes, now: int | None = None, max_skew_s: int = 120) -> VerifiedStore:
        """Verify signature and atomically record nonce. Distinct from order idempotency.

        An authenticated request consumes a nonce even if downstream delivery fails.
        Retries should be re-signed with a NEW nonce and the SAME order idempotency key.
        """
        try:
            normalized = {k.lower(): v for k, v in headers.items()}
            if any(k.lower() not in normalized for k in _REQUIRED):
                raise StoreAuthenticationError("Invalid store credentials")
            store_id = normalized["x-store-id"]
            key_id = normalized["x-store-key-id"]
            nonce = normalized["x-store-nonce"]
            ts_text = normalized["x-store-timestamp"]
            if not re.fullmatch(r"[0-9]{1,12}", ts_text):
                raise StoreAuthenticationError("Invalid store credentials")
            timestamp = int(ts_text)
            signature = _decode_b64url(normalized["x-store-signature"])
            if len(signature) != 64:
                raise StoreAuthenticationError("Invalid store credentials")
            message = signature_message(store_id=store_id, key_id=key_id,
                timestamp=timestamp, nonce=nonce, method=method, path=path, body=body)
            if now is None:
                now = int(time.time())
            if max_skew_s < 1 or abs(now - timestamp) > max_skew_s:
                raise StoreAuthenticationError("Invalid store credentials")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT public_key,revoked FROM store_public_keys WHERE store_id=? AND key_id=?",
                                      (store_id, key_id)).fetchone()
                if row is None or row[1]:
                    raise StoreAuthenticationError("Invalid store credentials")
                Ed25519PublicKey.from_public_bytes(row[0]).verify(signature, message)
                self.db.execute("INSERT INTO store_replay_nonces (store_id,key_id,nonce,expires_at) VALUES (?,?,?,?)",
                    (store_id, key_id, nonce, timestamp + max_skew_s + 1))
                # Old nonces may be removed only after their signed timestamp cannot be accepted.
                self.db.execute("DELETE FROM store_replay_nonces WHERE expires_at < ?", (now,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            return VerifiedStore(store_id, key_id, nonce, timestamp)
        except (ValueError, KeyError, InvalidSignature, sqlite3.IntegrityError, StoreAuthenticationError) as exc:
            raise StoreAuthenticationError("Invalid store credentials") from exc

    def close(self):
        self.db.close()
