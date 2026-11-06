from dataclasses import replace

from applications.storeguard.dispatch_admission import admit_work_item
from applications.storeguard.multi_agent_planner import AgentWorkItem
from policy.agent_capabilities import SRE_AGENT
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT


def work(agent=SRE_AGENT, action="investigate_store"):
    return AgentWorkItem(
        threat_id="WX-001",
        store_id="SG-002",
        agent_name=agent,
        action=action,
    )


def admit(item, scope=frozenset({"SG-002"}), incident="INC-001"):
    return admit_work_item(
        item,
        incident_id=incident,
        allowed_store_ids=scope,
    )


def test_registered_sre_is_ready_not_authorized():
    result = admit(work())
    assert result.status == "READY_FOR_GOVERNED_EXECUTION"


def test_registered_weather_agent_ready_for_governed_execution():
    result = admit(work(WEATHER_RESPONSE_AGENT, "assess_weather"))

    assert result.status == "READY_FOR_GOVERNED_EXECUTION"


def test_undeclared_capability_denied():
    result = admit(work(action="enter_protected"))
    assert result.status == "DENIED"


def test_out_of_scope_store_denied():
    result = admit(work(), scope=frozenset({"SG-009"}))
    assert result.status == "DENIED"


def test_missing_incident_denied():
    assert admit(work(), incident="").status == "DENIED"


def test_nonplanned_work_denied():
    assert admit(replace(work(), status="COMPLETED")).status == "DENIED"


def test_unknown_agent_denied():
    assert admit(work(agent="unknown-agent")).status == "DENIED"
