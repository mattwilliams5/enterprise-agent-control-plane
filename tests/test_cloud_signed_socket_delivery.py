"""Self-contained offline integration tests using a REAL localhost TCP socket."""
import json
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from applications.storeguard.cloud_dr.offline_signed_api import OfflineSQLiteLedger, app, offline_ledger_factory
from applications.storeguard.cloud_dr.signed_order_api import get_registry_path, get_ledger_factory
from applications.storeguard.cloud_dr.store_identity import (
    StoreIdentityRegistry, generate_private_key, public_key_bytes, sign_order_request,
)
from applications.storeguard.cloud_dr.order_queue import OrderQueue
from applications.storeguard.cloud_dr.delivery_reliability import DeliveryState
from applications.storeguard.cloud_dr.signed_queue_delivery import deliver_signed_queue
from applications.storeguard.cloud_dr.order_ledger import Order


@pytest.fixture
def signed_server(tmp_path, monkeypatch):
    registry_path = tmp_path / 'registry.sqlite3'
    secret_dir = tmp_path / 'private'
    secret_dir.mkdir()
    keys = {}
    registry = StoreIdentityRegistry(registry_path)
    for sid in ('1800', '1801'):
        key = generate_private_key()
        registry.enroll(sid, 'key-v1', public_key_bytes(key))
        (secret_dir / f'store-{sid}.ed25519').write_bytes(key.private_bytes_raw())
        keys[sid] = key
    registry.close()
    monkeypatch.setenv('STOREGUARD_OFFLINE_LEDGER_DB', str(tmp_path / 'ledger.sqlite3'))
    app.dependency_overrides[get_registry_path] = lambda: registry_path
    app.dependency_overrides[get_ledger_factory] = lambda: offline_ledger_factory
    # Choose a free loopback port; UVicorn may race for it in rare cases.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(app, host='127.0.0.1', port=port,
                            log_level='error', access_log=False, lifespan='off')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    url = f'http://127.0.0.1:{port}'
    try:
        while not server.started and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started, 'Uvicorn did not start'
        yield url, keys, registry_path, secret_dir, tmp_path
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.clear()


def post(client, key, sid='1800', order_id='ORDER1', amount=2599,
         idem='KEY1', *, reuse_headers=None):
    body = json.dumps({'order_id': order_id, 'amount_cents': amount,
                       'idempotency_key': idem}, separators=(',', ':')).encode()
    headers = reuse_headers or sign_order_request(key, store_id=sid,
                                                  key_id='key-v1', body=body)
    return client.post('/orders', content=body, headers=headers), headers


def test_real_socket_signed_and_fresh_retry(signed_server):
    url, keys, *_ = signed_server
    with httpx.Client(base_url=url, timeout=3) as client:
        a, headers = post(client, keys['1800'])
        assert a.status_code == 200 and a.json()['status'] == 'committed'
        replay, _ = post(client, keys['1800'], reuse_headers=headers)
        assert replay.status_code == 401
        retry, _ = post(client, keys['1800'])
        assert retry.status_code == 200 and retry.json()['status'] == 'duplicate'
        assert retry.json()['receipt_id'] == a.json()['receipt_id']


def test_real_socket_conflict_and_store_isolation(signed_server):
    url, keys, *_ = signed_server
    with httpx.Client(base_url=url, timeout=3) as client:
        assert post(client, keys['1800'])[0].status_code == 200
        assert post(client, keys['1800'], amount=3999, idem='KEY2')[0].status_code == 409
        other, _ = post(client, keys['1801'], sid='1801')
        assert other.status_code == 200 and other.json()['status'] == 'committed'
        assert other.json()['receipt_id'] != post(client, keys['1800'])[0].json()['receipt_id']


def test_real_socket_invalid_signature_and_dev_key(signed_server):
    url, keys, *_ = signed_server
    body = b'{"order_id":"ORDER1","amount_cents":2599,"idempotency_key":"KEY1"}'
    headers = sign_order_request(keys['1800'], store_id='1800', key_id='key-v1', body=body)
    with httpx.Client(base_url=url, timeout=3) as client:
        assert client.post('/orders', content=body + b' ', headers=headers).status_code == 401
        assert client.post('/orders', content=body, headers={**headers, 'X-API-Key':'dev'}).status_code == 401


def test_queue_to_real_socket_acknowledges_and_persists(signed_server):
    url, _, _, secret_dir, path = signed_server
    queue_db = path / 'queue.sqlite3'
    queue = OrderQueue(queue_db)
    queue.enqueue(Order('1800','QUEUE1',2599,'QUEUEKEY1'))
    queue.close()
    state = DeliveryState(queue_db)
    result = deliver_signed_queue(state, identity_directory=secret_dir,
                                  base_url=url, max_items=1)
    assert result[0]['outcome'] == 'acknowledged'
    state.close()
    queue = OrderQueue(queue_db)
    assert queue.pending() == []
    queue.close()


def test_queue_timeout_stays_pending_then_fresh_retry(signed_server):
    url, _, _, secret_dir, path = signed_server
    queue_db = path / 'queue.sqlite3'
    queue = OrderQueue(queue_db)
    queue.enqueue(Order('1800','QUEUE2',2599,'QUEUEKEY2'))
    queue.close()
    def timeout(request):
        raise httpx.ReadTimeout('lost acknowledgment')
    state = DeliveryState(queue_db, clock=lambda: 1000)
    result = deliver_signed_queue(state, identity_directory=secret_dir,
                                  base_url=url, max_items=1,
                                  transport=httpx.MockTransport(timeout))
    assert result[0]['outcome'] == 'unknown'
    assert state.inspect('1800','QUEUE2')['attempts'] == 1
    state.close()
    queue = OrderQueue(queue_db)
    assert len(queue.pending()) == 1
    queue.close()
    state = DeliveryState(queue_db, clock=lambda: 1003)
    recovered = deliver_signed_queue(state, identity_directory=secret_dir,
                                     base_url=url, max_items=1)
    assert recovered[0]['outcome'] == 'acknowledged'
    state.close()


def test_offline_ledger_survives_restart(tmp_path):
    db = tmp_path / 'orders.sqlite3'
    ledger = OfflineSQLiteLedger(db)
    order = Order('1800', 'ALPHA', 100, 'ALPHAKEY')
    first = ledger.submit(order)
    second = OfflineSQLiteLedger(db).submit(order)
    assert first['receipt_id'] == second['receipt_id']
    assert second['status'] == 'duplicate'


def test_client_fails_closed_for_remote_address(tmp_path):
    class State:
        def claim(self, **kwargs):
            raise AssertionError('Must reject URL before claims')
    with pytest.raises(ValueError):
        deliver_signed_queue(State(), identity_directory=tmp_path,
                             base_url='https://public.example.com')
