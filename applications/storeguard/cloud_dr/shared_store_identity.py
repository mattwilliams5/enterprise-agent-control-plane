"""Firestore-backed verification of StoreGuard protocol-v1 signed store requests.

No enrollment HTTP endpoint. Administrators provision public keys out of band.
Use a shared Firestore database in both app regions; this does not make the
Firestore database independently disaster-recoverable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from google.cloud import firestore

from applications.storeguard.cloud_dr.store_identity import (
    StoreAuthenticationError, VerifiedStore, _decode_b64url,
    _validate_id, signature_message,
)


@dataclass(frozen=True)
class SharedIdentityConfig:
    max_skew_s: int = 120


class FirestoreStoreIdentityVerifier:
    """Shared key lookup and atomic nonce consumption via Firestore transactions.

    A nonce is consumed before downstream order processing. Retry the SAME
    order idempotency key with a NEW signed nonce after uncertain outcomes.
    """
    def __init__(self, client, config: SharedIdentityConfig = SharedIdentityConfig()):
        self.client = client
        self.config = config

    @staticmethod
    def key_document_id(store_id: str, key_id: str) -> str:
        return sha256(f"{store_id}\0{key_id}".encode('ascii')).hexdigest()

    @staticmethod
    def nonce_document_id(store_id: str, key_id: str, nonce: str) -> str:
        return sha256(f"{store_id}\0{key_id}\0{nonce}".encode('ascii')).hexdigest()

    def verify(self, *, headers: dict[str, str], method: str, path: str,
               body: bytes, now: int | None = None) -> VerifiedStore:
        try:
            lower = {k.lower(): v for k, v in headers.items()}
            store_id = _validate_id(lower['x-store-id'], 'store_id')
            key_id = _validate_id(lower['x-store-key-id'], 'key_id')
            nonce = lower['x-store-nonce']
            ts_text = lower['x-store-timestamp']
            if not ts_text.isascii() or not ts_text.isdigit() or len(ts_text) > 12:
                raise ValueError('Invalid timestamp')
            timestamp = int(ts_text)
            signature = _decode_b64url(lower['x-store-signature'])
            if len(signature) != 64:
                raise ValueError('Invalid signature')
            message = signature_message(store_id=store_id, key_id=key_id,
                timestamp=timestamp, nonce=nonce, method=method, path=path, body=body)
            if now is None:
                now = int(time.time())
            skew = self.config.max_skew_s
            if skew < 1 or abs(timestamp - now) > skew:
                raise ValueError('Stale signed request')
        except (KeyError, ValueError, StoreAuthenticationError, TypeError) as exc:
            raise StoreAuthenticationError('Invalid store credentials') from exc

        key_ref = self.client.collection('storeguard_store_public_keys').document(
            self.key_document_id(store_id, key_id))
        nonce_ref = self.client.collection('storeguard_store_replay_nonces').document(
            self.nonce_document_id(store_id, key_id, nonce))
        transaction = self.client.transaction()

        @firestore.transactional
        def consume(tx):
            # Both reads precede writes. Concurrent claims for same nonce can
            # have at most one successful transaction under Firestore isolation.
            key_snap = key_ref.get(transaction=tx)
            nonce_snap = nonce_ref.get(transaction=tx)
            if not key_snap.exists or nonce_snap.exists:
                raise StoreAuthenticationError('Invalid store credentials')
            record = key_snap.to_dict() or {}
            public_key = record.get('public_key')
            if (record.get('store_id') != store_id or record.get('key_id') != key_id
                or record.get('revoked') is not False
                or not isinstance(public_key, bytes) or len(public_key) != 32):
                raise StoreAuthenticationError('Invalid store credentials')
            try:
                Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
            except (InvalidSignature, ValueError) as exc:
                raise StoreAuthenticationError('Invalid store credentials') from exc
            tx.create(nonce_ref, {
                'store_id': store_id, 'key_id': key_id,
                'nonce_hash': sha256(nonce.encode('ascii')).hexdigest(),
                'signed_at': timestamp, 'expires_at_unix': timestamp + skew + 1,
                'created_at': firestore.SERVER_TIMESTAMP,
            })

        try:
            consume(transaction)
        except StoreAuthenticationError:
            raise
        except Exception:
            # Firestore transport/unavailability/transaction errors must not be
            # turned into authentication denial; caller should return 503.
            raise
        return VerifiedStore(store_id, key_id, nonce, timestamp)


def provision_store_public_key(*, client, store_id: str, key_id: str, public_key: bytes):
    """Admin-only create operation. No overwrite, reactivation, or HTTP exposure.

    Never call from a store request. Intended for a separately authorized
    operator/CI identity with provision-only Firestore permissions.
    """
    store_id = _validate_id(store_id, 'store_id')
    key_id = _validate_id(key_id, 'key_id')
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError('Expected a 32-byte Ed25519 public key')
    Ed25519PublicKey.from_public_bytes(public_key)
    ref = client.collection('storeguard_store_public_keys').document(
        FirestoreStoreIdentityVerifier.key_document_id(store_id, key_id))
    ref.create({'store_id': store_id, 'key_id': key_id,
                'public_key': public_key, 'revoked': False,
                'created_at': firestore.SERVER_TIMESTAMP})
