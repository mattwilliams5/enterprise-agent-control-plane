"""Offline signed-only HTTP boundary tests; never contact Google Cloud."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from applications.storeguard.cloud_dr.signed_order_api import (
    app, get_ledger_factory, get_registry_path,
)
from applications.storeguard.cloud_dr.store_identity import (
    StoreIdentityRegistry, generate_private_key, public_key_bytes,
    sign_order_request,
)

BODY = b'{"order_id":"ORDER-1","amount_cents":2599,"idempotency_key":"KEY-1"}'


class Ledger:
    def __init__(self):
        self.orders = []

    def submit(self, order):
        self.orders.append(order)
        return {"status": "committed", "store_id": order.store_id,
                "order_id": order.order_id, "receipt_id": "test-receipt"}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "identities.sqlite3"
    key = generate_private_key()
    registry = StoreIdentityRegistry(path)
    registry.enroll("1847", "key-a", public_key_bytes(key))
    registry.close()
    ledger = Ledger()
    app.dependency_overrides[get_registry_path] = lambda: path
    app.dependency_overrides[get_ledger_factory] = lambda: (lambda: ledger)
    with TestClient(app) as client:
        yield client, path, key, ledger
    app.dependency_overrides.clear()


def signed(key, body=BODY, **kw):
    return sign_order_request(key, store_id=kw.get("store_id", "1847"),
                              key_id=kw.get("key_id", "key-a"), body=body,
                              nonce=kw.get("nonce"))


def test_valid_signature_and_verified_store(setup):
    client, _, key, ledger = setup
    response = client.post("/orders", content=BODY, headers=signed(key))
    assert response.status_code == 200
    assert response.json()["store_id"] == "1847"
    assert ledger.orders[0].store_id == "1847"


def test_no_credentials_fails_closed(setup):
    client, _, _, ledger = setup
    assert client.post("/orders", content=BODY).status_code == 401
    assert ledger.orders == []


def test_dev_api_key_not_accepted(setup):
    client, _, _, ledger = setup
    r = client.post("/orders", content=BODY,
                    headers={"X-Store-ID": "1847", "X-API-Key": "anything"})
    assert r.status_code == 401
    assert not ledger.orders


def test_even_signed_request_rejects_dev_key_header(setup):
    client, _, key, _ = setup
    h = signed(key)
    h["X-API-Key"] = "unused"
    assert client.post("/orders", content=BODY, headers=h).status_code == 401


def test_tampering_raw_body_rejected(setup):
    client, _, key, ledger = setup
    assert client.post("/orders", content=BODY + b" ", headers=signed(key)).status_code == 401
    assert ledger.orders == []


def test_replay_cannot_commit_twice(setup):
    client, _, key, ledger = setup
    h = signed(key)
    assert client.post("/orders", content=BODY, headers=h).status_code == 200
    assert client.post("/orders", content=BODY, headers=h).status_code == 401
    assert len(ledger.orders) == 1


def test_new_nonce_allows_same_idempotent_order(setup):
    client, _, key, ledger = setup
    assert client.post("/orders", content=BODY, headers=signed(key)).status_code == 200
    assert client.post("/orders", content=BODY, headers=signed(key)).status_code == 200
    assert len(ledger.orders) == 2  # Real ledger enforces idempotency downstream.


def test_other_store_header_cannot_impersonate(setup):
    client, _, key, ledger = setup
    h = signed(key)
    h["X-Store-ID"] = "1848"
    assert client.post("/orders", content=BODY, headers=h).status_code == 401
    assert ledger.orders == []


def test_revoked_key_rejected(setup):
    client, path, key, ledger = setup
    r = StoreIdentityRegistry(path)
    r.revoke("1847", "key-a")
    r.close()
    assert client.post("/orders", content=BODY, headers=signed(key)).status_code == 401
    assert ledger.orders == []


def test_invalid_signed_payload_rejected_after_auth(setup):
    client, _, key, ledger = setup
    body = b'{"order_id":"INVALID SPACE","amount_cents":2599,"idempotency_key":"KEY-1"}'
    assert client.post("/orders", content=body, headers=signed(key, body)).status_code == 422
    assert ledger.orders == []


def test_duplicate_identity_header_rejected(setup):
    client, _, key, ledger = setup
    h = list(signed(key).items())
    h.append(("X-Store-ID", "1847"))
    assert client.post("/orders", content=BODY, headers=h).status_code == 401
    assert ledger.orders == []


def test_unconfigured_registry_rejected(setup):
    client, _, key, ledger = setup
    app.dependency_overrides.pop(get_registry_path)
    # Do not rely on developer environment for testing.
    old = __import__('os').environ.pop('STOREGUARD_IDENTITY_DB', None)
    try:
        assert client.post('/orders', content=BODY, headers=signed(key)).status_code == 503
    finally:
        if old is not None:
            __import__('os').environ['STOREGUARD_IDENTITY_DB'] = old
    assert ledger.orders == []


def test_health_is_not_an_order_endpoint(setup):
    client, _, _, ledger = setup
    assert client.get('/health').json()['authentication'] == 'signed-only-local'
    assert not ledger.orders
