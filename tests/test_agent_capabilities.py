from policy.agent_capabilities import (
    SRE_AGENT,
    get_agent_capabilities,
    is_capability_declared,
)
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT


def test_weather_agent_has_read_only_capabilities():
    capabilities = get_agent_capabilities(WEATHER_RESPONSE_AGENT)
    assert {c.action for c in capabilities} == {
        "assess_weather",
        "recommend_protection",
    }
    assert all(c.read_only for c in capabilities)


def test_sre_agent_can_investigate():
    assert is_capability_declared(SRE_AGENT, "investigate_store")


def test_weather_agent_cannot_investigate():
    assert not is_capability_declared(
        WEATHER_RESPONSE_AGENT, "investigate_store"
    )


def test_state_changing_actions_not_declared():
    for action in (
        "enter_protected",
        "enter_maintenance",
        "enter_recovery",
        "return_normal",
    ):
        assert not is_capability_declared(
            WEATHER_RESPONSE_AGENT, action
        )
        assert not is_capability_declared(SRE_AGENT, action)


def test_unknown_agent_has_no_capabilities():
    assert get_agent_capabilities("unknown-agent") == frozenset()
    assert not is_capability_declared(
        "unknown-agent", "assess_weather"
    )


def test_recovery_agent_has_no_capabilities():
    assert get_agent_capabilities(
        "storeguard-recovery-agent"
    ) == frozenset()
