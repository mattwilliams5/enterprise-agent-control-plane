import pytest

from applications.storeguard.cloud_dr.store_simulator import (
    STORE_IDS,
    generate_orders,
    run_simulation,
    summarize,
)


def test_forty_stores():
    assert len(STORE_IDS) == 40
    assert len(set(STORE_IDS)) == 40


def test_eighty_unique_orders():
    orders = generate_orders(2)
    assert len(orders) == 80
    assert len({o.order_id for o in orders}) == 80
    assert len({o.idempotency_key for o in orders}) == 80


def test_simulation_summary():
    results = run_simulation(generate_orders(2))
    summary = summarize(results)

    assert summary["total"] == 80
    assert summary["stores"] == 40
    assert summary["statuses"] == {"simulated": 80}


def test_order_amounts():
    for order in generate_orders(2):
        assert 500 <= order.amount_cents <= 25000


def test_invalid_order_count():
    with pytest.raises(ValueError):
        generate_orders(0)

    with pytest.raises(ValueError):
        generate_orders(11)
