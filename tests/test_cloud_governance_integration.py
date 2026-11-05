"""Offline integration: Firestore registry + audit + execution gate."""
from uuid import uuid4

import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied, AgentExecutionGate, AgentIntent, VerifiedAgent,
)
from applications.storeguard.cloud_dr.firestore_agent_audit import (
    FirestoreDecisionAudit,
)
from applications.storeguard.cloud_dr.firestore_agent_registry import (
    FirestoreAgentRegistry,
)

DATABASE = "storeguard-executive-evidence"
AGENT = "storeguard-weather-response-agent"
SUBJECT = "verified-vault-entity"


class Snapshot:
    def __init__(self, value):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return dict(self.value) if self.exists else None


class Document:
    def __init__(self, db, collection, key):
        self.db, self.collection, self.key = db, collection, key

    def get(self):
        self.db.reads += 1
        if self.db.fail:
            raise RuntimeError("Firestore unavailable")
        return Snapshot(self.db.documents.get((self.collection, self.key)))

    def create(self, data):
        if self.db.fail:
            raise RuntimeError("Firestore unavailable")
        key = (self.collection, self.key)
        if key in self.db.documents:
            raise RuntimeError("Duplicate evidence")
        self.db.documents[key] = dict(data)


class Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def document(self, key):
        return Document(self.db, self.name, key)


class FakeFirestore:
    _database = DATABASE

    def __init__(self):
        self.documents = {
            ("storeguard_agent_registry", AGENT): {
                "agent_id": AGENT,
                "approved": True,
                "status": "active",
                "revoked": False,
                "vault_entity_id": SUBJECT,
            }
        }
        self.reads = 0
        self.fail = False

    def collection(self, name):
        return Collection(self, name)


class MockIdentity:
    def __init__(self):
        self.calls = 0

    def verify_fresh(self, evidence, *, run_id):
        self.calls += 1
        return VerifiedAgent(AGENT, evidence, f"proof-{self.calls}")


class ScopedAuthorizer:
    def __init__(self, registry):
        self.registry = registry

    def authorize(self, *, identity, intent, run_id):
        return (
            self.registry.matches_identity(
                intent.agent_id, identity.workload_subject
            )
            and intent.store_id == "1800"
            and intent.action == "assess_weather"
            and intent.incident_id == "INC-1"
            and intent.delegation_id == "DEL-1"
        )


def setup():
    db = FakeFirestore()
    registry = FirestoreAgentRegistry(client=db, database=DATABASE)
    audit = FirestoreDecisionAudit(client=db, database=DATABASE)
    identity = MockIdentity()
    gate = AgentExecutionGate(
        identity=identity,
        registry=registry,
        authorizer=ScopedAuthorizer(registry),
        audit=audit,
    )
    intent = AgentIntent(AGENT, "INC-1", "1800",
                         "assess_weather", "DEL-1")
    return db, identity, gate, intent


def test_separate_runs_have_fresh_identity_and_evidence():
    db, identity, gate, intent = setup()
    first = gate.authorize_run(intent, SUBJECT)
    second = gate.authorize_run(intent, SUBJECT)

    assert first != second
    assert identity.calls == 2
    assert db.reads >= 4
    for run_id in (first, second):
        assert db.documents[
            ("storeguard_agent_decisions", run_id)
        ]["decision"] == "allow"


def test_revocation_blocks_next_run():
    db, identity, gate, intent = setup()
    gate.authorize_run(intent, SUBJECT)

    db.documents[("storeguard_agent_registry", AGENT)]["revoked"] = True

    with pytest.raises(AgentDenied) as error:
        gate.authorize_run(intent, SUBJECT)

    assert error.value.reason == "inactive_or_revoked"
    assert identity.calls == 2
    assert db.documents[
        ("storeguard_agent_decisions", error.value.run_id)
    ]["decision"] == "deny"


def test_wrong_authenticated_entity_denied():
    db, identity, gate, intent = setup()

    with pytest.raises(AgentDenied) as error:
        gate.authorize_run(intent, "wrong-entity")

    assert error.value.reason == "scope_denied"


def test_firestore_outage_fails_closed():
    db, identity, gate, intent = setup()
    db.fail = True

    with pytest.raises(AgentDenied):
        gate.authorize_run(intent, SUBJECT)


def test_unapproved_store_denied():
    db, identity, gate, intent = setup()
    intent = AgentIntent(AGENT, "INC-1", "9999",
                         "assess_weather", "DEL-1")

    with pytest.raises(AgentDenied) as error:
        gate.authorize_run(intent, SUBJECT)

    assert error.value.reason == "scope_denied"
