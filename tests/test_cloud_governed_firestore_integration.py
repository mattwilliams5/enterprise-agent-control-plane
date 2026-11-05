"""Offline integration of real cloud governance adapters.

Firestore storage and cryptographic identity verification are simulated.
No cloud credentials or live Vault access required.
"""
import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied, AgentIntent, VerifiedAgent,
)
from applications.storeguard.cloud_dr.cloud_agent_authorizer import (
    CloudAgentAuthorizer,
)
from applications.storeguard.cloud_dr.cloud_governed_runner import (
    CloudGovernedReadOnlyRunner,
)
from applications.storeguard.cloud_dr.firestore_agent_registry import (
    FirestoreAgentRegistry,
)
from applications.storeguard.cloud_dr.firestore_agent_audit import (
    FirestoreDecisionAudit,
)
from applications.storeguard.cloud_dr.firestore_tool_audit import (
    FirestoreToolAudit,
)

DATABASE = "storeguard-executive-evidence"
AGENT = "storeguard-weather-response-agent"
ENTITY = "verified-vault-entity"


class Snapshot:
    def __init__(self, value):
        self.exists = value is not None
        self.value = value

    def to_dict(self):
        return dict(self.value) if self.exists else None


class Document:
    def __init__(self, db, collection, key):
        self.db, self.collection, self.key = db, collection, key

    def get(self):
        self.db.registry_reads += 1
        if self.db.fail_reads:
            raise RuntimeError("Registry unavailable")
        if (self.db.revoke_on_read is not None
                and self.db.registry_reads >= self.db.revoke_on_read):
            self.db.documents[("storeguard_agent_registry", AGENT)]["revoked"] = True
        return Snapshot(self.db.documents.get((self.collection, self.key)))

    def create(self, record):
        if self.db.fail_writes:
            raise RuntimeError("Evidence storage unavailable")
        key = (self.collection, self.key)
        if key in self.db.documents:
            raise RuntimeError("Duplicate evidence")
        self.db.documents[key] = dict(record)


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
                "vault_entity_id": ENTITY,
            }
        }
        self.registry_reads = 0
        self.revoke_on_read = None
        self.fail_reads = False
        self.fail_writes = False

    def collection(self, name):
        return Collection(self, name)

    def events(self, collection):
        return [
            doc for (name, _), doc in self.documents.items()
            if name == collection
        ]


class TrustedTestIdentity:
    """Test-only verifier; NOT cryptographic authentication."""
    def __init__(self):
        self.calls = 0

    def verify_fresh(self, evidence, *, run_id):
        self.calls += 1
        if evidence != "trusted-fixture":
            raise ValueError("Invalid test evidence")
        return VerifiedAgent(
            agent_id=AGENT,
            workload_subject=ENTITY,
            evidence_id=f"verified-{run_id}",
        )


def setup():
    db = FakeFirestore()
    registry = FirestoreAgentRegistry(client=db, database=DATABASE)
    identity = TrustedTestIdentity()
    executed = []

    authorizer = CloudAgentAuthorizer(
        registry=registry,
        delegation_check=lambda **kw: kw["intent"].delegation_id == "DEL-1",
        scope_check=lambda **kw: (
            kw["intent"].incident_id == "INC-1"
            and kw["intent"].store_id == "1800"
        ),
    )

    def assess_weather(intent):
        executed.append(intent.store_id)
        return {"status": "assessed"}

    runner = CloudGovernedReadOnlyRunner(
        identity_verifier=identity,
        registry=registry,
        authorizer=authorizer,
        decision_audit=FirestoreDecisionAudit(
            client=db, database=DATABASE
        ),
        tool_audit=FirestoreToolAudit(
            client=db, database=DATABASE
        ),
        handlers={"assess_weather": assess_weather},
    )

    intent = AgentIntent(
        AGENT, "INC-1", "1800", "assess_weather", "DEL-1"
    )
    return db, identity, executed, runner, intent


def test_authorized_tool_records_decisions_and_outcomes():
    db, identity, executed, runner, intent = setup()

    result = runner.execute(intent=intent, evidence="trusted-fixture")

    assert result["result"] == {"status": "assessed"}
    assert executed == ["1800"]
    assert identity.calls == 2

    decisions = db.events("storeguard_agent_decisions")
    events = db.events("storeguard_agent_tool_events")

    assert len(decisions) == 2
    assert all(item["decision"] == "allow" for item in decisions)
    assert {item["event_type"] for item in events} == {
        "STARTED", "COMPLETED"
    }


def test_revocation_between_checks_blocks_tool():
    db, identity, executed, runner, intent = setup()
    db.revoke_on_read = 3

    with pytest.raises(AgentDenied):
        runner.execute(intent=intent, evidence="trusted-fixture")

    assert executed == []
    decisions = db.events("storeguard_agent_decisions")
    assert [item["decision"] for item in decisions].count("deny") == 1
    assert not any(
        item["event_type"] == "STARTED"
        for item in db.events("storeguard_agent_tool_events")
    )


def test_invalid_delegation_blocks_tool():
    db, identity, executed, runner, intent = setup()
    bad = AgentIntent(AGENT, "INC-1", "1800", "assess_weather", "INVALID")

    with pytest.raises(AgentDenied):
        runner.execute(intent=bad, evidence="trusted-fixture")

    assert executed == []


def test_firestore_write_outage_blocks_execution():
    db, identity, executed, runner, intent = setup()
    db.fail_writes = True

    with pytest.raises(AgentDenied) as exc:
        runner.execute(intent=intent, evidence="trusted-fixture")

    assert exc.value.reason == "audit_unavailable"
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert executed == []
    assert not db.events("storeguard_agent_tool_events")


def test_invalid_identity_evidence_blocks_execution():
    db, identity, executed, runner, intent = setup()

    with pytest.raises(AgentDenied):
        runner.execute(intent=intent, evidence="untrusted")

    assert executed == []
