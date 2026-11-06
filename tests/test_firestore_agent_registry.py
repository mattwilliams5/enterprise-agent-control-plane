"""Offline tests for shared StoreGuard agent registration."""
import pytest

from applications.storeguard.cloud_dr.firestore_agent_registry import (
    COLLECTION,
    EVIDENCE_DATABASE,
    FirestoreAgentRegistry,
)

AGENT = "storeguard-weather-response-agent"
ENTITY = "vault-entity-123"


def active_record():
    return {
        "agent_id": AGENT,
        "approved": True,
        "status": "active",
        "revoked": False,
        "vault_entity_id": ENTITY,
    }


class Snapshot:
    def __init__(self, value):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return self.value.copy() if isinstance(self.value, dict) else self.value


class FakeDocument:
    def __init__(self, db, agent_id):
        self.db = db
        self.agent_id = agent_id

    def get(self):
        self.db.reads += 1
        if self.db.fail:
            raise RuntimeError("Firestore unavailable")
        return Snapshot(self.db.records.get(self.agent_id))


class FakeCollection:
    def __init__(self, db):
        self.db = db

    def document(self, agent_id):
        return FakeDocument(self.db, agent_id)


class FakeFirestore:
    _database = EVIDENCE_DATABASE

    def __init__(self):
        self.records = {AGENT: active_record()}
        self.reads = 0
        self.fail = False

    def collection(self, name):
        assert name == COLLECTION
        return FakeCollection(self)


def registry(db=None):
    return FirestoreAgentRegistry(
        client=db if db is not None else FakeFirestore(),
        database=EVIDENCE_DATABASE,
    )


def test_active_agent_allowed():
    assert registry().is_active(AGENT)


def test_identity_matches_registered_entity():
    assert registry().matches_identity(AGENT, ENTITY)
    assert not registry().matches_identity(AGENT, "other-entity")


def test_revoked_agent_denied_on_fresh_read():
    db = FakeFirestore()
    reg = registry(db)
    assert reg.is_active(AGENT)
    db.records[AGENT]["revoked"] = True
    assert not reg.is_active(AGENT)
    assert db.reads == 2


@pytest.mark.parametrize("changes", [
    {"approved": False},
    {"status": "inactive"},
    {"revoked": True},
    {"vault_entity_id": ""},
    {"vault_entity_id": None},
    {"agent_id": "different-agent"},
])
def test_invalid_registration_denied(changes):
    db = FakeFirestore()
    db.records[AGENT].update(changes)
    assert not registry(db).is_active(AGENT)


def test_missing_agent_denied():
    assert not registry().is_active("unknown-agent")


def test_invalid_agent_identifier_denied():
    db = FakeFirestore()
    assert not registry(db).is_active("../other")
    assert db.reads == 0


def test_database_unavailable_never_allows():
    db = FakeFirestore()
    db.fail = True
    with pytest.raises(RuntimeError):
        registry(db).is_active(AGENT)


@pytest.mark.parametrize("database", ["(default)", "", "other"])
def test_wrong_database_rejected(database):
    with pytest.raises(ValueError):
        FirestoreAgentRegistry(
            client=FakeFirestore(), database=database
        )


def test_client_database_mismatch_denied():
    db = FakeFirestore()
    db._database = "(default)"
    with pytest.raises(ValueError):
        registry(db)
