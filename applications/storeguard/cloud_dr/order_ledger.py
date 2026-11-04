"""Firestore-backed StoreGuard order ledger with canonical order identity."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from google.cloud import firestore


class IdempotencyConflict(Exception):
    """An existing order identity was used with conflicting data."""


@dataclass(frozen=True)
class Order:
    store_id: str
    order_id: str
    amount_cents: int
    idempotency_key: str

    def validate(self):
        for name, value in (
            ("store_id", self.store_id),
            ("order_id", self.order_id),
            ("idempotency_key", self.idempotency_key),
        ):
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,128}", value
            ):
                raise ValueError(f"Invalid {name}")

        if (
            isinstance(self.amount_cents, bool)
            or not isinstance(self.amount_cents, int)
            or not 0 < self.amount_cents <= 100_000_000
        ):
            raise ValueError("Invalid amount_cents")

    def fingerprint(self):
        payload = {
            "store_id": self.store_id,
            "order_id": self.order_id,
            "amount_cents": self.amount_cents,
        }
        return sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()


class FirestoreOrderLedger:
    def __init__(self, client=None):
        self.client = client if client is not None else firestore.Client()

    @staticmethod
    def _digest(*parts):
        return sha256(
            json.dumps(parts, separators=(",", ":")).encode()
        ).hexdigest()

    def submit(self, order: Order):
        order.validate()

        canonical_id = self._digest(order.store_id, order.order_id)
        key_id = self._digest(order.store_id, order.idempotency_key)

        canonical_ref = (
            self.client.collection("storeguard_order_identity")
            .document(canonical_id)
        )
        key_ref = (
            self.client.collection("storeguard_order_keys")
            .document(key_id)
        )
        receipt_ref = (
            self.client.collection("storeguard_orders")
            .document(key_id)
        )

        transaction = self.client.transaction()

        @firestore.transactional
        def commit(tx):
            # All transaction reads precede writes.
            canonical = canonical_ref.get(transaction=tx)
            key_record = key_ref.get(transaction=tx)

            if key_record.exists:
                existing_key = key_record.to_dict()

                if existing_key["fingerprint"] != order.fingerprint():
                    raise IdempotencyConflict(
                        "Idempotency key reused with different order data"
                    )

                return {
                    "status": "duplicate",
                    "store_id": order.store_id,
                    "order_id": order.order_id,
                    "receipt_id": existing_key["receipt_id"],
                }

            if canonical.exists:
                existing = canonical.to_dict()

                if existing["fingerprint"] != order.fingerprint():
                    raise IdempotencyConflict(
                        "Order ID reused with different order data"
                    )

                tx.create(key_ref, {
                    "store_id": order.store_id,
                    "order_id": order.order_id,
                    "fingerprint": order.fingerprint(),
                    "receipt_id": existing["receipt_id"],
                })

                return {
                    "status": "duplicate",
                    "store_id": order.store_id,
                    "order_id": order.order_id,
                    "receipt_id": existing["receipt_id"],
                }

            tx.create(canonical_ref, {
                "store_id": order.store_id,
                "order_id": order.order_id,
                "fingerprint": order.fingerprint(),
                "receipt_id": key_id,
                "created_at": firestore.SERVER_TIMESTAMP,
            })

            tx.create(key_ref, {
                "store_id": order.store_id,
                "order_id": order.order_id,
                "fingerprint": order.fingerprint(),
                "receipt_id": key_id,
            })

            tx.create(receipt_ref, {
                "store_id": order.store_id,
                "order_id": order.order_id,
                "amount_cents": order.amount_cents,
                "idempotency_key": order.idempotency_key,
                "fingerprint": order.fingerprint(),
                "created_at": firestore.SERVER_TIMESTAMP,
            })

            return {
                "status": "committed",
                "store_id": order.store_id,
                "order_id": order.order_id,
                "receipt_id": key_id,
            }

        return commit(transaction)
