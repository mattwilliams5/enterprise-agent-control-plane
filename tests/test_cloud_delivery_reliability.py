from types import SimpleNamespace
import httpx
import pytest
from applications.storeguard.cloud_dr.order_queue import OrderQueue
from applications.storeguard.cloud_dr.regional_router import Region, RegionalRouter
from applications.storeguard.cloud_dr.delivery_reliability import DeliveryState
from applications.storeguard.cloud_dr.reliable_delivery import deliver_reliably
from applications.storeguard.cloud_dr.regional_health import RegionalHealth
from applications.storeguard.cloud_dr.health_aware_router import HealthAwareRouter


def make_order(order_id='o1', key='k1'):
    return SimpleNamespace(store_id='1847', order_id=order_id, amount_cents=2500, idempotency_key=key)


@pytest.fixture
def env(tmp_path):
    t = [100.0]
    q = OrderQueue(tmp_path / 'orders.sqlite')
    q.enqueue(make_order())
    state = DeliveryState(q.path, clock=lambda: t[0])
    yield q, state, t
    state.close()
    q.close()


def test_atomic_claims_prevent_double_delivery(env):
    q, first, _ = env
    second = DeliveryState(q.path, clock=first.clock)
    assert first.claim().order_id == 'o1'
    assert second.claim() is None
    second.close()


def test_expired_lease_reclaimed_and_stale_ack_fenced(env):
    q, state, t = env
    old = state.claim(lease_seconds=10)
    t[0] += 11
    new = state.claim()
    assert new.claim_token != old.claim_token
    assert state.settle(old, outcome='acknowledged', receipt_id='bad') is False
    assert q.pending()
    assert state.settle(new, outcome='acknowledged', receipt_id='good')
    assert q.pending() == []


def test_restart_recovers_expired_claim(env):
    q, state, t = env
    assert state.claim(lease_seconds=10)
    state.close()
    t[0] += 11
    restored = DeliveryState(q.path, clock=lambda: t[0])
    assert restored.claim() is not None
    restored.close()


def test_unknown_commit_retry_preserves_identity_and_backoff(env):
    q, state, t = env
    claim = state.claim()
    assert state.settle(claim, outcome='unknown', base_delay=5)
    assert state.claim() is None
    t[0] += 5
    retry = state.claim()
    assert retry.idempotency_key == claim.idempotency_key
    assert retry.order_id == claim.order_id
    assert state.inspect('1847', 'o1')['attempts'] == 1


def test_rejection_quarantines_and_explicit_release(env):
    _, state, _ = env
    claim = state.claim()
    state.settle(claim, outcome='rejected', status_code=409)
    assert state.claim() is None
    assert state.inspect('1847', 'o1')['last_status_code'] == 409
    assert state.release_quarantine('1847', 'o1')
    assert state.claim() is not None


def test_no_credentials_quarantined_locally(env):
    q, state, _ = env
    class Explode:
        def submit(self, *args):
            raise AssertionError('must not send')
    events = deliver_reliably(state, Explode(), {})
    assert events[0].outcome == 'no_credentials'
    assert state.inspect('1847', 'o1')['disposition'] == 'quarantined'
    assert len(q.pending()) == 1


def test_worker_success_acknowledged(env):
    q, state, _ = env
    class Acknowledged:
        def submit(self, payload, headers):
            assert payload['idempotency_key'] == 'k1'
            return {'outcome': 'acknowledged', 'receipt_id': 'receipt', 'region': 'us-central1'}
    events = deliver_reliably(state, Acknowledged(), {'1847': 'local-test-only'})
    assert events[0].outcome == 'acknowledged'
    assert q.pending() == []


def test_lost_ack_replayed_after_backoff(env):
    q, state, t = env
    seen = []
    class LostAck:
        def submit(self, payload, headers):
            seen.append(payload.copy())
            if len(seen) == 1:
                raise httpx.ReadTimeout('commit succeeded, ack lost')
            return {'outcome': 'acknowledged', 'receipt_id': 'same-receipt'}
    r = LostAck()
    assert deliver_reliably(state, r, {'1847': 'local-only'})[0].outcome == 'unknown'
    assert q.pending()
    assert deliver_reliably(state, r, {'1847': 'local-only'}) == []
    t[0] += 2
    assert deliver_reliably(state, r, {'1847': 'local-only'})[0].outcome == 'acknowledged'
    assert seen[0] == seen[1]


def test_health_survives_restart(env):
    q, _, t = env
    h = RegionalHealth(q.path, clock=lambda: t[0], min_primary_probes=2, hold_seconds=30)
    h.enter_recovery('primary timeout')
    h.close()
    again = RegionalHealth(q.path, clock=lambda: t[0], min_primary_probes=2, hold_seconds=30)
    assert again.snapshot()['mode'] == 'recovery'
    assert not again.failback_if_ready()
    again.close()


def test_failback_requires_probe_streak_hold_and_explicit_action(env):
    q, _, t = env
    h = RegionalHealth(q.path, clock=lambda: t[0], min_primary_probes=3, hold_seconds=60)
    h.enter_recovery('test')
    h.record_primary_probe(True)
    h.record_primary_probe(False)
    h.record_primary_probe(True)
    h.record_primary_probe(True)
    t[0] += 61
    assert not h.failback_if_ready()
    h.record_primary_probe(True)
    assert h.snapshot()['mode'] == 'recovery'
    assert h.failback_if_ready()
    assert h.snapshot()['mode'] == 'primary'
    h.close()


def test_recovery_pinning_never_contacts_primary(env):
    q, _, t = env
    visited = []
    def handler(request):
        visited.append(request.url.host)
        return httpx.Response(503)
    router = RegionalRouter(Region('primary', 'https://primary.example.test'),
                            Region('recovery', 'https://recovery.example.test'),
                            transport=httpx.MockTransport(handler))
    h = RegionalHealth(q.path, clock=lambda: t[0])
    h.enter_recovery('test')
    result = HealthAwareRouter(router, h).submit(
        {'order_id': 'o1', 'amount_cents': 2500, 'idempotency_key': 'k1'},
        {'X-Store-ID': '1847', 'X-API-Key': 'local'})
    assert result['outcome'] == 'unknown'
    assert visited == ['recovery.example.test']
    h.close()


def test_successful_failover_persists_recovery_mode(env):
    q, _, t = env
    visited = []
    def handler(request):
        visited.append(request.url.host)
        if request.url.host.startswith('primary'):
            return httpx.Response(503)
        return httpx.Response(200, json={'status': 'committed', 'store_id': '1847',
                'order_id': 'o1', 'receipt_id': 'abc'})
    router = RegionalRouter(Region('primary', 'https://primary.example.test'),
                            Region('recovery', 'https://recovery.example.test'),
                            transport=httpx.MockTransport(handler))
    h = RegionalHealth(q.path, clock=lambda: t[0])
    wrapper = HealthAwareRouter(router, h)
    payload = {'order_id': 'o1', 'amount_cents': 2500, 'idempotency_key': 'k1'}
    headers = {'X-Store-ID': '1847', 'X-API-Key': 'local'}
    assert wrapper.submit(payload, headers)['outcome'] == 'acknowledged'
    assert h.snapshot()['mode'] == 'recovery'
    assert wrapper.submit(payload, headers)['outcome'] == 'acknowledged'
    assert visited == ['primary.example.test', 'recovery.example.test', 'recovery.example.test']
    h.close()


def test_expired_lease_cannot_ack_before_reclaim(env):
    q, state, t = env
    claimed = state.claim(lease_seconds=3)
    t[0] += 4
    assert state.settle(claimed, outcome='acknowledged', receipt_id='late') is False
    assert len(q.pending()) == 1


def test_delivery_states_durable_after_restart(env):
    q, state, t = env
    claimed = state.claim()
    state.settle(claimed, outcome='rejected', status_code=409)
    state.close()
    restored = DeliveryState(q.path, clock=lambda: t[0])
    assert restored.inspect('1847', 'o1')['disposition'] == 'quarantined'
    assert restored.claim() is None
    restored.close()
