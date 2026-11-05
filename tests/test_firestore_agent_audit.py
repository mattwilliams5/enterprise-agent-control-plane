"""Offline, credential-free tests for cloud agent decision persistence."""
from uuid import uuid4

import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied,
    AgentExecutionGate,
    AgentIntent,
    VerifiedAgent,
)
from applications.storeguard.cloud_dr.firestore_agent_audit import (
    COLLECTION,
    EVIDENCE_DATABASE,
    FirestoreDecisionAudit,
)


class FakeDocument:
    def __init__(self, store, document_id):
        self.store = store
        self.document_id = document_id

    def create(self, data):
        if self.store.fail:
            raise RuntimeError("Firestore unavailable")
        if self.document_id in self.store.records:
            raise RuntimeError("Document already exists")
        self.store.records[self.document_id] = data.copy()


class FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def document(self, document_id):
        assert self.name == COLLECTION
        return FakeDocument(self.store, document_id)


class FakeFirestore:
    _database = EVIDENCE_DATABASE

    def __init__(self):
        self.records = {}
        self.fail = False

    def collection(self, name):
        return FakeCollection(self, name)


def make_record(run_id=None, decision="allow"):
    return {
        "run_id": run_id or uuid4().hex,
        "agent_id": "storeguard-weather-response-agent",
        "incident_id": "INC-100",
        "store_id": "1800",
        "action": "assess_weather",
        "delegation_id": "DEL-100",
        "verified_subject": "vault-entity",
        "evidence_id": "vault-request",
        "decision": decision,
        "reason": "authorized",
    }


def make_audit(client=None):
    return FirestoreDecisionAudit(
        client=client or FakeFirestore(),
        database=EVIDENCE_DATABASE,
    )


def test_creates_durable_decision_record():
    store = FakeFirestore()
    audit = make_audit(store)
    record = make_record()
    audit.append(record)
    assert store.records[record["run_id"]]["decision"] == "allow"
    assert store.records[record["run_id"]]["recorded_at"]


def test_denial_can_be_recorded():
    store = FakeFirestore()
    record = make_record(decision="deny")
    make_audit(store).append(record)
    assert store.records[record["run_id"]]["decision"] == "deny"


def test_duplicate_run_cannot_overwrite():
    store = FakeFirestore()
    audit = make_audit(store)
    record = make_record()
    audit.append(record)
    with pytest.raises(RuntimeError):
        audit.append({**record, "decision": "deny"})
    assert store.records[record["run_id"]]["decision"] == "allow"


def test_firestore_failure_propagates():
    store = FakeFirestore()
    store.fail = True
    with pytest.raises(RuntimeError):
        make_audit(store).append(make_record())


@pytest.mark.parametrize("database", ["(default)", "other", ""])
def test_wrong_database_rejected(database):
    with pytest.raises(ValueError):
        FirestoreDecisionAudit(
            client=FakeFirestore(),
            database=database,
        )


def test_database_mismatch_rejected():
    store = FakeFirestore()
    store._database = "(default)"
    with pytest.raises(ValueError):
        make_audit(store)


def test_invalid_run_id_rejected():
    with pytest.raises(ValueError):
        make_audit().append(make_record(run_id="bad-id"))


def test_credentials_not_persisted():
    store = FakeFirestore()
    record = make_record()
    record["client_token"] = "DO_NOT_STORE"
    record["secret_id"] = "DO_NOT_STORE"
    make_audit(store).append(record)
    saved = store.records[record["run_id"]]
    assert "client_token" not in saved
    assert "secret_id" not in saved


class Identity:
    def verify_fresh(self, evidence, *, run_id):
        return VerifiedAgent("agent-1", "subject-1", "proof-1")


class Registry:
    def is_active(self, agent_id):
        return True


class Authorizer:
    def authorize(self, *, identity, intent, run_id):
        return True


def test_failed_audit_blocks_execution_authorization():
    store = FakeFirestore()
    store.fail = True

    gate = AgentExecutionGate(
        identity=Identity(),
        registry=Registry(),
        authorizer=Authorizer(),
        audit=make_audit(store),
    )

    intent = AgentIntent(
        "agent-1", "INC-1", "1800",
        "assess_weather", "DEL-1",
    )

    with pytest.raises(AgentDenied) as exc:
        gate.authorize_run(intent, "test-evidence")

    assert exc.value.reason == "audit_unavailable"
