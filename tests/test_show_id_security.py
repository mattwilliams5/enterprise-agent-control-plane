"""Security regression tests for StoreGuard Show ID."""

from dataclasses import replace

import pytest

from identity.show_id import IdentityDenied, verify_agent_identity
from identity.vault_identity import VerifiedVaultIdentity
from policy.engine import authorize_investigation
from registry.registry import get_agent_record


AGENT = "sre-troubleshooting-agent"
REGISTERED_ENTITY = get_agent_record(AGENT).vault_entity_id


def identity(entity_id=REGISTERED_ENTITY):
    return VerifiedVaultIdentity(
        entity_id=entity_id,
        policies=("storeguard-investigator",),
        token_ttl=300,
    )


def test_registered_agent_identity_matches():
    result = verify_agent_identity(AGENT, identity())
    assert result.verified is True
    assert result.vault_entity_id == REGISTERED_ENTITY


def test_unregistered_agent_denied():
    with pytest.raises(IdentityDenied):
        verify_agent_identity("unknown-agent", identity())


def test_mismatched_vault_identity_denied():
    with pytest.raises(IdentityDenied):
        verify_agent_identity(AGENT, identity("wrong-entity"))


def test_unapproved_agent_denied(monkeypatch):
    import identity.show_id as show_id

    record = replace(get_agent_record(AGENT), approved=False)
    monkeypatch.setattr(
        show_id, "get_agent_record", lambda name: record
    )

    with pytest.raises(IdentityDenied):
        verify_agent_identity(AGENT, identity())


def test_authorized_store_allowed():
    assert authorize_investigation(
        agent_name=AGENT,
        store_id="1847",
        incident_id="INC-001",
        allowed_store_ids=frozenset({"1847"}),
    )


def test_out_of_scope_store_denied():
    assert not authorize_investigation(
        agent_name=AGENT,
        store_id="9999",
        incident_id="INC-001",
        allowed_store_ids=frozenset({"1847"}),
    )


def test_missing_incident_denied():
    assert not authorize_investigation(
        agent_name=AGENT,
        store_id="1847",
        incident_id="",
        allowed_store_ids=frozenset({"1847"}),
    )
