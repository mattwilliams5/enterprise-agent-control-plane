import pytest

from applications.storeguard.cloud_dr.order_ledger import (
    Order,
    IdempotencyConflict,
)


def test_valid_order():
    order = Order(
        store_id="1847",
        order_id="ORDER-001",
        amount_cents=2599,
        idempotency_key="store1847-order001",
    )
    order.validate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", "../invalid"),
        ("order_id", ""),
        ("idempotency_key", "invalid key"),
        ("amount_cents", -100),
        ("amount_cents", 0),
        ("amount_cents", True),
        ("amount_cents", 100_000_001),
    ],
)
def test_invalid_order(field, value):
    data = {
        "store_id": "1847",
        "order_id": "ORDER-001",
        "amount_cents": 2599,
        "idempotency_key": "key-001",
    }
    data[field] = value

    with pytest.raises(ValueError):
        Order(**data).validate()


def test_same_order_has_same_fingerprint():
    order = Order("1847", "ORDER-001", 2599, "key-001")
    assert order.fingerprint() == order.fingerprint()


def test_different_order_has_different_fingerprint():
    first = Order("1847", "ORDER-001", 2599, "key-001")
    second = Order("1847", "ORDER-001", 3999, "key-001")

    assert first.fingerprint() != second.fingerprint()


def test_idempotency_conflict_exception():
    with pytest.raises(IdempotencyConflict):
        raise IdempotencyConflict("Conflicting order")
