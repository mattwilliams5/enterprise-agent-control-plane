"""Offline tests; no live Vault or Google Cloud access."""
import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied, AgentIntent, VerifiedAgent,
)
from applications.storeguard.cloud_dr.cloud_governed_runner import (
    CloudGovernedReadOnlyRunner,
)


AGENT = "storeguard-weather-response-agent"


class Identity:
    def __init__(self):
        self.calls = 0

    def verify_fresh(self, evidence, *, run_id):
        self.calls += 1
        return VerifiedAgent(AGENT, "vault-entity", f"proof-{self.calls}")


class Registry:
    def __init__(self):
        self.calls = 0
        self.active = True
        self.revoke_on_second_check = False

    def is_active(self, agent_id):
        self.calls += 1
        if self.revoke_on_second_check and self.calls >= 2:
            return False
        return self.active


class Authorizer:
    def authorize(self, *, identity, intent, run_id):
        return intent.store_id == "1800"


class DecisionAudit:
    def __init__(self):
        self.records = []
        self.fail = False

    def append(self, record):
        if self.fail:
            raise RuntimeError("decision audit unavailable")
        self.records.append(dict(record))


class ToolAudit:
    def __init__(self):
        self.events = []
        self.fail = False

    def append(self, **event):
        if self.fail:
            raise RuntimeError("tool audit unavailable")
        self.events.append(dict(event))


def setup():
    identity = Identity()
    registry = Registry()
    decisions = DecisionAudit()
    tools = ToolAudit()
    executed = []

    def handler(intent):
        executed.append(intent.store_id)
        return {"status": "assessed"}

    runner = CloudGovernedReadOnlyRunner(
        identity_verifier=identity,
        registry=registry,
        authorizer=Authorizer(),
        decision_audit=decisions,
        tool_audit=tools,
        handlers={"assess_weather": handler},
    )
    intent = AgentIntent(
        AGENT, "INC-1", "1800", "assess_weather", "DEL-1"
    )
    return runner, intent, identity, registry, decisions, tools, executed


def test_authorized_execution():
    runner, intent, identity, registry, decisions, tools, executed = setup()
    result = runner.execute(intent=intent, evidence="trusted-test-evidence")
    assert result["result"]["status"] == "assessed"
    assert result["authorization_run_id"] != result["action_gate_run_id"]
    assert identity.calls == 2
    assert registry.calls == 2
    assert len(decisions.records) == 2
    assert [e["event_type"] for e in tools.events] == [
        "STARTED", "COMPLETED"
    ]
    assert executed == ["1800"]


def test_revocation_between_checks_blocks_execution():
    runner, intent, identity, registry, decisions, tools, executed = setup()
    registry.revoke_on_second_check = True

    with pytest.raises(AgentDenied):
        runner.execute(intent=intent, evidence="trusted-test-evidence")

    assert executed == []
    assert decisions.records[-1]["decision"] == "deny"


def test_decision_audit_failure_blocks_execution():
    runner, intent, identity, registry, decisions, tools, executed = setup()
    decisions.fail = True

    with pytest.raises(AgentDenied):
        runner.execute(intent=intent, evidence="trusted-test-evidence")

    assert executed == []


def test_tool_audit_failure_blocks_execution():
    runner, intent, identity, registry, decisions, tools, executed = setup()
    tools.fail = True

    with pytest.raises(RuntimeError, match="tool audit unavailable"):
        runner.execute(intent=intent, evidence="trusted-test-evidence")

    assert executed == []


def test_out_of_scope_store_denied():
    runner, intent, identity, registry, decisions, tools, executed = setup()
    intent = AgentIntent(
        AGENT, "INC-1", "9999", "assess_weather", "DEL-1"
    )

    with pytest.raises(AgentDenied):
        runner.execute(intent=intent, evidence="trusted-test-evidence")

    assert executed == []
