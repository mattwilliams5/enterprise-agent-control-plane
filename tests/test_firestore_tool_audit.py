"""Offline tests for create-only protected-tool evidence."""
from uuid import uuid4

import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import AgentIntent
from applications.storeguard.cloud_dr.firestore_tool_audit import (
    COLLECTION, DATABASE, FirestoreToolAudit,
)

AGENT = "storeguard-weather-response-agent"


class FakeDocument:
    def __init__(self, db, key):
        self.db, self.key = db, key

    def create(self, record):
        if self.db.fail:
            raise OSError("Firestore unavailable")
        if self.key in self.db.events:
            raise ValueError("Duplicate event ID")
        self.db.events[self.key] = dict(record)


class FakeCollection:
    def __init__(self, db):
        self.db = db

    def document(self, key):
        return FakeDocument(self.db, key)


class FakeFirestore:
    _database = DATABASE

    def __init__(self):
        self.events = {}
        self.fail = False

    def collection(self, name):
        assert name == COLLECTION
        return FakeCollection(self)


def intent():
    return AgentIntent(
        AGENT, "INC-100", "1800", "assess_weather", "DEL-100"
    )


def make(db=None):
    return FirestoreToolAudit(
        client=db if db is not None else FakeFirestore(),
        database=DATABASE,
    )


def record(audit, **changes):
    options = dict(
        action_run_id=uuid4().hex,
        event_type="STARTED",
        intent=intent(),
        reason="allowed",
    )
    options.update(changes)
    return audit.append(**options)


def test_event_is_persisted():
    db = FakeFirestore()
    event_id = record(make(db))
    assert db.events[event_id]["event_type"] == "STARTED"


def test_multiple_events_share_action_run_id():
    db = FakeFirestore()
    audit = make(db)
    run_id = uuid4().hex
    first = record(audit, action_run_id=run_id)
    second = record(
        audit, action_run_id=run_id,
        event_type="COMPLETED", reason="success"
    )
    assert first != second
    assert len(db.events) == 2
    assert all(
        event["action_run_id"] == run_id
        for event in db.events.values()
    )


def test_storage_failure_propagates():
    db = FakeFirestore()
    db.fail = True
    with pytest.raises(OSError):
        record(make(db))


def test_invalid_run_id_rejected():
    with pytest.raises(ValueError):
        record(make(), action_run_id="../unsafe")


def test_unknown_event_rejected():
    with pytest.raises(ValueError):
        record(make(), event_type="GRANT_ADMIN")


def test_missing_intent_rejected():
    with pytest.raises(ValueError):
        record(make(), intent=None)


def test_credentials_are_not_stored():
    db = FakeFirestore()
    event_id = record(make(db))
    saved = db.events[event_id]
    assert "client_token" not in saved
    assert "secret_id" not in saved
    assert "role_id" not in saved


@pytest.mark.parametrize("database", ["", "(default)", "other"])
def test_invalid_database_rejected(database):
    with pytest.raises(ValueError):
        FirestoreToolAudit(
            client=FakeFirestore(),
            database=database,
        )


def test_client_database_mismatch_rejected():
    db = FakeFirestore()
    db._database = "(default)"
    with pytest.raises(ValueError):
        make(db)
