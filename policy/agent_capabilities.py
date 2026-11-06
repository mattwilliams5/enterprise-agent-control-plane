"""Static agent capability catalog; not execution authorization."""

from dataclasses import dataclass

from policy.storeguard_actions import WEATHER_RESPONSE_AGENT

SRE_AGENT = "sre-troubleshooting-agent"


@dataclass(frozen=True)
class AgentCapability:
    agent_name: str
    action: str
    read_only: bool


CAPABILITIES = frozenset({
    AgentCapability(
        WEATHER_RESPONSE_AGENT,
        "assess_weather",
        True,
    ),
    AgentCapability(
        WEATHER_RESPONSE_AGENT,
        "recommend_protection",
        True,
    ),
    AgentCapability(
        SRE_AGENT,
        "investigate_store",
        True,
    ),
})


def get_agent_capabilities(agent_name: str):
    """Return declared capabilities without granting execution rights."""
    return frozenset(
        capability
        for capability in CAPABILITIES
        if capability.agent_name == agent_name
    )


def is_capability_declared(agent_name: str, action: str) -> bool:
    """Check eligibility only; never use as execution authorization."""
    return any(
        capability.agent_name == agent_name
        and capability.action == action
        for capability in CAPABILITIES
    )
