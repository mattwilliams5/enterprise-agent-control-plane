from unittest.mock import Mock, patch

import pytest

from applications.storeguard.cloud_dr.order_ledger import (
    FirestoreOrderLedger,
    IdempotencyConflict,
    Order,
)


class Snapshot:
    def __init__(self, data=None):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self, database, collection, document_id):
        self.database = database
        self.key = (collection, document_id)

    def get(self, transaction=None):
        return Snapshot(self.database.get(self.key))


class FakeCollection:
    def __init__(self, database, name):
        self.database = database
        self.name = name

    def document(self, document_id):
        return FakeDocument(self.database, self.name, document_id)


class FakeTransaction:
    def __init__(self, database):
        self.database = database
        self.writes = []

    def create(self, ref, data):
        self.writes.append((ref.key, data))

    def commit(self):
        for key, _ in self.writes:
            if key in self.database:
                raise RuntimeError("Document already exists")
        for key, data in self.writes:
            self.database[key] = data


class FakeClient:
    def __init__(self):
        self.database = {}

    def collection(self, name):
        return FakeCollection(self.database, name)

    def transaction(self):
        return FakeTransaction(self.database)


@pytest.fixture
def ledger():
    client = FakeClient()

    # Simulate the Firestore transaction decorator locally.
    def transactional(fn):
        def wrapper(tx):
            result = fn(tx)
            tx.commit()
            return result
        return wrapper

    with patch(
        "applications.storeguard.cloud_dr.order_ledger.firestore.transactional",
        transactional,
    ):
        yield FirestoreOrderLedger(client=client)


def test_first_order_commits(ledger):
    result = ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-1"))
    assert result["status"] == "committed"


def test_same_key_returns_original_receipt(ledger):
    order = Order("1847", "ORDER-1", 2599, "KEY-1")
    first = ledger.submit(order)
    second = ledger.submit(order)

    assert second["status"] == "duplicate"
    assert second["receipt_id"] == first["receipt_id"]


def test_new_key_same_order_returns_original_receipt(ledger):
    first = ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-1"))
    second = ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-2"))

    assert second["status"] == "duplicate"
    assert second["receipt_id"] == first["receipt_id"]


def test_same_order_different_amount_rejected(ledger):
    ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-1"))

    with pytest.raises(IdempotencyConflict):
        ledger.submit(Order("1847", "ORDER-1", 3999, "KEY-2"))


def test_same_key_different_order_rejected(ledger):
    ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-1"))

    with pytest.raises(IdempotencyConflict):
        ledger.submit(Order("1847", "ORDER-2", 2599, "KEY-1"))


def test_different_stores_can_reuse_order_id(ledger):
    first = ledger.submit(Order("1847", "ORDER-1", 2599, "KEY-1"))
    second = ledger.submit(Order("1848", "ORDER-1", 2599, "KEY-1"))

    assert first["status"] == "committed"
    assert second["status"] == "committed"
    assert first["receipt_id"] != second["receipt_id"]
