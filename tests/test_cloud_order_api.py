import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient

from applications.storeguard.cloud_dr.order_api import (
    app,
    get_ledger,
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STOREGUARD_DEV_API_KEY", "test-secret")
    monkeypatch.setenv("STOREGUARD_DEV_STORE_ID", "1847")

    ledger = Mock()
    ledger.submit.return_value = {
        "status": "committed",
        "store_id": "1847",
        "order_id": "ORDER-001",
        "receipt_id": "a" * 64,
    }

    app.dependency_overrides[get_ledger] = lambda: ledger

    with TestClient(app) as api:
        yield api, ledger

    app.dependency_overrides.clear()


def test_health(client):
    api, _ = client
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthorized_order(client):
    api, ledger = client
    response = api.post(
        "/orders",
        headers={"X-Store-ID": "1847", "X-API-Key": "wrong"},
        json={
            "order_id": "ORDER-001",
            "amount_cents": 2599,
            "idempotency_key": "key-001",
        },
    )
    assert response.status_code == 401
    ledger.submit.assert_not_called()


def test_wrong_store_rejected(client):
    api, ledger = client
    response = api.post(
        "/orders",
        headers={"X-Store-ID": "9999", "X-API-Key": "test-secret"},
        json={
            "order_id": "ORDER-001",
            "amount_cents": 2599,
            "idempotency_key": "key-001",
        },
    )
    assert response.status_code == 403
    ledger.submit.assert_not_called()


def test_authorized_order(client):
    api, ledger = client
    response = api.post(
        "/orders",
        headers={"X-Store-ID": "1847", "X-API-Key": "test-secret"},
        json={
            "order_id": "ORDER-001",
            "amount_cents": 2599,
            "idempotency_key": "key-001",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "committed"
    ledger.submit.assert_called_once()


def test_invalid_amount_rejected(client):
    api, ledger = client
    response = api.post(
        "/orders",
        headers={"X-Store-ID": "1847", "X-API-Key": "test-secret"},
        json={
            "order_id": "ORDER-001",
            "amount_cents": -100,
            "idempotency_key": "key-001",
        },
    )
    assert response.status_code == 422
    ledger.submit.assert_not_called()
