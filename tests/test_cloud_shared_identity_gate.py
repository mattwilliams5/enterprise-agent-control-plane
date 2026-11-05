"""Offline tests. No live Cloud resources, secrets, or Vault needed."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from applications.storeguard.cloud_dr.store_identity import (
    StoreAuthenticationError, generate_private_key, public_key_bytes, sign_order_request,
)
from applications.storeguard.cloud_dr import shared_store_identity as shared
from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied, AgentExecutionGate, AgentIntent, VerifiedAgent,
)
from applications.storeguard.cloud_dr.cloud_signed_order_api import app, get_cloud_components

BODY = b'{"order_id":"O1","amount_cents":123,"idempotency_key":"K1"}'


class Snap:
    def __init__(self, data):
        self.exists = data is not None
        self.data = data
    def to_dict(self):
        return self.data


class Ref:
    def __init__(self, client, coll, doc):
        self.client, self.key = client, (coll, doc)
    def get(self, transaction=None):
        return Snap(self.client.data.get(self.key))
    def create(self, data):
        with self.client.lock:
            if self.key in self.client.data:
                raise ValueError('Exists')
            self.client.data[self.key] = data


class Collection:
    def __init__(self, client, name):
        self.client, self.name = client, name
    def document(self, doc):
        return Ref(self.client, self.name, doc)


class Tx:
    def __init__(self, client):
        self.client = client
        self.writes = []
    def create(self, ref, data):
        self.writes.append((ref, data))


class FakeClient:
    def __init__(self):
        self.data, self.lock = {}, threading.RLock()
    def collection(self, name):
        return Collection(self, name)
    def transaction(self):
        return Tx(self)


@pytest.fixture
def harness(monkeypatch):
    c = FakeClient()
    def transactional(fn):
        def runner(tx):
            with c.lock:  # serializable fake for deterministic unit tests
                result = fn(tx)
                for ref, data in tx.writes:
                    if ref.key in c.data:
                        raise ValueError('Already created')
                    c.data[ref.key] = data
                return result
        return runner
    monkeypatch.setattr(shared.firestore, 'transactional', transactional)
    key = generate_private_key()
    shared.provision_store_public_key(client=c, store_id='1800', key_id='v1',
                                      public_key=public_key_bytes(key))
    return c, key, shared.FirestoreStoreIdentityVerifier(c)


def sign(key, **kw):
    return sign_order_request(key, store_id='1800', key_id='v1', body=kw.get('body', BODY),
                              timestamp=kw.get('timestamp', 1000), nonce=kw.get('nonce', 'a' * 24))


def verify(v, h, **kw):
    return v.verify(headers=h, method='POST', path='/orders', body=kw.get('body', BODY), now=1000)


def test_valid_signed_request(harness):
    _, key, v = harness
    assert verify(v, sign(key)).store_id == '1800'


def test_replay_rejected_after_success(harness):
    _, key, v = harness
    headers = sign(key)
    verify(v, headers)
    with pytest.raises(StoreAuthenticationError):
        verify(v, headers)


def test_modified_body_denied(harness):
    _, key, v = harness
    with pytest.raises(StoreAuthenticationError):
        verify(v, sign(key), body=BODY + b' ')


def test_wrong_store_denied(harness):
    _, key, v = harness
    headers = sign(key)
    headers['X-Store-ID'] = '1801'
    with pytest.raises(StoreAuthenticationError):
        verify(v, headers)


def test_revoked_key_denied(harness):
    c, key, v = harness
    doc = v.key_document_id('1800', 'v1')
    c.data[('storeguard_store_public_keys', doc)]['revoked'] = True
    with pytest.raises(StoreAuthenticationError):
        verify(v, sign(key))


def test_unauthorized_nonce_not_consumed(harness):
    c, key, v = harness
    headers = sign(key)
    with pytest.raises(StoreAuthenticationError):
        verify(v, headers, body=BODY + b' ')
    assert verify(v, headers).store_id == '1800'


def test_concurrent_nonce_claim_one_winner(harness):
    _, key, v = harness
    headers = sign(key)
    def attempt(_):
        try:
            verify(v, headers)
            return True
        except StoreAuthenticationError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1


def test_no_key_overwrite(harness):
    c, key, _ = harness
    with pytest.raises(ValueError):
        shared.provision_store_public_key(client=c, store_id='1800', key_id='v1',
                                          public_key=public_key_bytes(key))


def test_timestamp_expired(harness):
    _, key, v = harness
    with pytest.raises(StoreAuthenticationError):
        verify(v, sign(key, timestamp=100))


class Identity:
    def __init__(self):
        self.calls = 0
        self.fail = False
    def verify_fresh(self, evidence, *, run_id):
        self.calls += 1
        if self.fail:
            raise ValueError('bad evidence')
        return VerifiedAgent(evidence, 'vault-subject', f'evidence-{self.calls}')


class Registry:
    active = True
    def is_active(self, agent_id):
        return self.active


class Policy:
    allowed = True
    def authorize(self, *, identity, intent, run_id):
        return self.allowed and intent.store_id == '1800' and intent.action == 'protect'


class Audit:
    def __init__(self):
        self.records = []
        self.fail = False
    def append(self, record):
        if self.fail:
            raise RuntimeError('audit down')
        self.records.append(record)


@pytest.fixture
def gate():
    identity, registry, policy, audit = Identity(), Registry(), Policy(), Audit()
    return AgentExecutionGate(identity=identity, registry=registry,
                              authorizer=policy, audit=audit), identity, registry, policy, audit


INTENT = AgentIntent('agent-1', 'incident-1', '1800', 'protect', 'delegation-1')


def test_each_agent_run_rechecks_identity_and_new_run_id(gate):
    g, identity, _, _, audit = gate
    a = g.authorize_run(INTENT, 'agent-1')
    b = g.authorize_run(INTENT, 'agent-1')
    assert a != b and identity.calls == 2
    assert len(audit.records) == 2
    assert audit.records[0]['decision'] == 'allow'


def test_revoked_agent_denied_and_audited(gate):
    g, _, registry, _, audit = gate
    registry.active = False
    with pytest.raises(AgentDenied):
        g.authorize_run(INTENT, 'agent-1')
    assert audit.records[-1]['reason'] == 'inactive_or_revoked'


def test_scoped_action_denied(gate):
    g, _, _, _, audit = gate
    with pytest.raises(AgentDenied):
        g.authorize_run(AgentIntent('agent-1', 'incident-1', '1801', 'protect', 'd'), 'agent-1')
    assert audit.records[-1]['reason'] == 'scope_denied'


def test_wrong_identity_denied(gate):
    g, _, _, _, audit = gate
    with pytest.raises(AgentDenied):
        g.authorize_run(INTENT, 'agent-other')
    assert audit.records[-1]['reason'] == 'identity_mismatch'


def test_failed_cryptographic_verification_denied(gate):
    g, identity, _, _, audit = gate
    identity.fail = True
    with pytest.raises(AgentDenied):
        g.authorize_run(INTENT, 'agent-1')
    assert audit.records[-1]['decision'] == 'deny'


def test_audit_failure_prevents_allow(gate):
    g, _, _, _, audit = gate
    audit.fail = True
    with pytest.raises(AgentDenied) as ex:
        g.authorize_run(INTENT, 'agent-1')
    assert ex.value.reason == 'audit_unavailable'


def test_cloud_api_rejects_dev_key_before_backend(harness):
    from applications.storeguard.cloud_dr.store_identity import sign_order_request
    client, key, verifier = harness
    class Ledger:
        def submit(self, order):
            return {'status': 'committed', 'store_id': order.store_id,
                    'order_id': order.order_id, 'receipt_id': 'r'}
    app.dependency_overrides[get_cloud_components] = lambda: (verifier, Ledger())
    try:
        with TestClient(app) as http:
            headers = sign_order_request(key, store_id='1800', key_id='v1', body=BODY)
            headers['X-API-Key'] = 'forbidden'
            assert http.post('/orders', content=BODY, headers=headers).status_code == 401
    finally:
        app.dependency_overrides.clear()
