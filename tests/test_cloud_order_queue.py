from types import SimpleNamespace

import pytest

from applications.storeguard.cloud_dr.order_queue import OrderQueue


@pytest.fixture
def queue(tmp_path):
    q = OrderQueue(tmp_path / "orders.db")
    yield q
    q.close()


def order(amount=2599, key="KEY-1"):
    return SimpleNamespace(
        store_id="1847",
        order_id="ORDER-1",
        amount_cents=amount,
        idempotency_key=key,
    )


def test_enqueue(queue):
    queue.enqueue(order())
    assert len(queue.pending()) == 1


def test_duplicate_enqueue(queue):
    queue.enqueue(order())
    queue.enqueue(order())
    assert len(queue.pending()) == 1


def test_conflicting_enqueue(queue):
    queue.enqueue(order())
    with pytest.raises(ValueError):
        queue.enqueue(order(amount=3999))


def test_acknowledgment(queue):
    queue.enqueue(order())
    queue.acknowledge("1847", "ORDER-1", "receipt-123")
    assert queue.pending() == []


def test_survives_restart(tmp_path):
    path = tmp_path / "persistent.db"
    first = OrderQueue(path)
    first.enqueue(order())
    first.close()

    second = OrderQueue(path)
    assert len(second.pending()) == 1
    second.close()
