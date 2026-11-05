"""Offline cloud authorization boundary tests."""
from dataclasses import replace

import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentIntent, VerifiedAgent,
)
from applications.storeguard.cloud_dr.cloud_agent_authorizer import (
    CloudAgentAuthorizer,
)

AGENT = "storeguard-weather-response-agent"
ENTITY = "verified-vault-entity"


class Registry:
    def __init__(self):
        self.active = True
        self.entity = ENTITY
        self.reads = 0

    def matches_identity(self, agent_id, entity_id):
        self.reads += 1
        return (
            self.active
            and agent_id == AGENT
            and entity_id == self.entity
        )


def build(delegation=True, scope=True):
    registry = Registry()
    authorizer = CloudAgentAuthorizer(
        registry=registry,
        delegation_check=lambda **kw: delegation,
        scope_check=lambda **kw: scope,
    )
    identity = VerifiedAgent(AGENT, ENTITY, "vault-proof")
    intent = AgentIntent(
        AGENT, "INC-100", "1800",
        "assess_weather", "DEL-100",
    )
    return registry, authorizer, identity, intent


def check(authorizer, identity, intent):
    return authorizer.authorize(
        identity=identity, intent=intent, run_id="run-1"
    )


def test_valid_agent_allowed():
    _, auth, identity, intent = build()
    assert check(auth, identity, intent) is True


def test_revocation_blocks_next_check():
    registry, auth, identity, intent = build()
    assert check(auth, identity, intent)
    registry.active = False
    assert check(auth, identity, intent) is False
    assert registry.reads == 2


def test_wrong_vault_entity_denied():
    _, auth, identity, intent = build()
    identity = replace(identity, workload_subject="wrong")
    assert check(auth, identity, intent) is False


def test_agent_impersonation_denied():
    _, auth, identity, intent = build()
    intent = replace(intent, agent_id="sre-troubleshooting-agent")
    assert check(auth, identity, intent) is False


@pytest.mark.parametrize("action", [
    "enter_protected", "unknown", "investigate_store"
])
def test_undeclared_capability_denied(action):
    _, auth, identity, intent = build()
    assert not check(auth, identity, replace(intent, action=action))


@pytest.mark.parametrize("delegation,scope", [
    (False, True), (True, False), (False, False)
])
def test_delegation_or_scope_denied(delegation, scope):
    _, auth, identity, intent = build(delegation, scope)
    assert not check(auth, identity, intent)


@pytest.mark.parametrize("field", [
    "incident_id", "store_id", "delegation_id", "action"
])
def test_missing_intent_field_denied(field):
    _, auth, identity, intent = build()
    assert not check(auth, identity, replace(intent, **{field: ""}))


def test_registry_failure_never_authorizes():
    _, auth, identity, intent = build()

    def unavailable(*args):
        raise RuntimeError("registry unavailable")

    auth.registry.matches_identity = unavailable

    with pytest.raises(RuntimeError):
        check(auth, identity, intent)


def test_missing_trusted_validator_rejected():
    with pytest.raises(TypeError):
        CloudAgentAuthorizer(
            registry=Registry(),
            delegation_check=None,
            scope_check=lambda **kw: True,
        )
