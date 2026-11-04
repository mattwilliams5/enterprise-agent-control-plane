"""Integration tests against the real SQLite queue and regional router interfaces."""
from types import SimpleNamespace

import httpx
import pytest

from applications.storeguard.cloud_dr.order_queue import OrderQueue
from applications.storeguard.cloud_dr.regional_router import Region, RegionalRouter
from applications.storeguard.cloud_dr.queue_router_delivery import deliver_pending_via_router

PRIMARY = Region('us-central1', 'https://primary.example.test')
RECOVERY = Region('us-east4', 'https://recovery.example.test')
CREDS = {'1847': 'test-only'}


def order(order_id='ORDER-1', key='KEY-1'):
    return SimpleNamespace(store_id='1847', order_id=order_id, amount_cents=2599, idempotency_key=key)


def accepted(request, status='committed', receipt='r' * 64):
    payload = __import__('json').loads(request.content)
    return httpx.Response(200, json={'status': status, 'store_id': request.headers['X-Store-ID'],
                                     'order_id': payload['order_id'], 'receipt_id': receipt})


def router(handler):
    return RegionalRouter(PRIMARY, RECOVERY, transport=httpx.MockTransport(handler))


@pytest.fixture
def queue(tmp_path):
    q = OrderQueue(tmp_path / 'orders.sqlite')
    yield q
    q.close()


def test_primary_commit_acknowledges_and_preserves_key(queue):
    queue.enqueue(order())
    sent = []
    def handler(request):
        sent.append(__import__('json').loads(request.content))
        return accepted(request)
    out = deliver_pending_via_router(queue, router(handler), CREDS)
    assert [e.outcome for e in out] == ['acknowledged']
    assert sent[0]['idempotency_key'] == 'KEY-1'
    assert queue.pending() == []
    assert queue.db.execute('SELECT receipt_id FROM orders').fetchone()[0] == 'r' * 64


def test_503_fails_over_without_mutating_order_identity(queue):
    queue.enqueue(order())
    seen = []
    def handler(request):
        seen.append((request.url.host, bytes(request.content)))
        return httpx.Response(503) if request.url.host == 'primary.example.test' else accepted(request)
    out = deliver_pending_via_router(queue, router(handler), CREDS)
    assert out[0].region == 'us-east4'
    assert [x[0] for x in seen] == ['primary.example.test', 'recovery.example.test']
    assert seen[0][1] == seen[1][1]
    assert not queue.pending()


def test_lost_ack_primary_then_duplicate_recovery(queue):
    queue.enqueue(order())
    ledger = set()
    def handler(request):
        payload = __import__('json').loads(request.content)
        identity = (request.headers['X-Store-ID'], payload['order_id'], payload['idempotency_key'])
        if request.url.host == 'primary.example.test':
            ledger.add(identity)  # primary committed before acknowledgment vanished
            raise httpx.ReadTimeout('lost response')
        assert identity in ledger
        return accepted(request, status='duplicate')
    out = deliver_pending_via_router(queue, router(handler), CREDS)
    assert out[0].outcome == 'acknowledged'
    assert len(ledger) == 1
    assert not queue.pending()


def test_both_endpoints_fail_queue_survives_restart(tmp_path):
    path = tmp_path / 'store.sqlite'
    q = OrderQueue(path)
    q.enqueue(order())
    def offline(request):
        raise httpx.ConnectError('offline')
    assert deliver_pending_via_router(q, router(offline), CREDS)[0].outcome == 'unknown'
    q.close()
    q = OrderQueue(path)
    assert q.pending()[0]['idempotency_key'] == 'KEY-1'
    assert deliver_pending_via_router(q, router(lambda r: accepted(r, 'duplicate')), CREDS)[0].outcome == 'acknowledged'
    assert not q.pending()
    q.close()


@pytest.mark.parametrize('code', [401, 403, 409, 422])
def test_rejected_not_acknowledged_or_failed_over(queue, code):
    queue.enqueue(order())
    seen = []
    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(code)
    out = deliver_pending_via_router(queue, router(handler), CREDS)
    assert out[0].outcome == 'rejected'
    assert out[0].status_code == code
    assert seen == ['primary.example.test']
    assert len(queue.pending()) == 1


def test_invalid_receipt_stays_pending(queue):
    queue.enqueue(order())
    def invalid(request):
        return httpx.Response(200, json={'status': 'committed', 'store_id': '1847',
                                         'order_id': 'ORDER-1', 'receipt_id': None})
    assert deliver_pending_via_router(queue, router(invalid), CREDS)[0].outcome == 'unknown'
    assert len(queue.pending()) == 1


def test_no_credentials_never_sends(queue):
    queue.enqueue(order())
    calls = []
    def handler(request):
        calls.append(1)
        return accepted(request)
    out = deliver_pending_via_router(queue, router(handler), {})
    assert out[0].outcome == 'no_credentials'
    assert not calls
    assert len(queue.pending()) == 1


def test_bounded_batch_no_repeat_loop(queue):
    for i in range(3):
        queue.enqueue(order(f'ORDER-{i}', f'KEY-{i}'))
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(503)
    out = deliver_pending_via_router(queue, router(handler), CREDS, max_items=2)
    assert len(out) == 2
    assert len(calls) == 4  # two regions per order; never same row twice in batch
    assert len(queue.pending()) == 3
    with pytest.raises(ValueError):
        deliver_pending_via_router(queue, router(handler), CREDS, max_items=0)


def test_corrupt_router_response_no_false_ack(queue):
    queue.enqueue(order())
    class BadRouter:
        def submit(self, payload, headers):
            return {'outcome': 'acknowledged', 'receipt_id': ''}
    assert deliver_pending_via_router(queue, BadRouter(), CREDS)[0].outcome == 'unknown'
    assert len(queue.pending()) == 1
