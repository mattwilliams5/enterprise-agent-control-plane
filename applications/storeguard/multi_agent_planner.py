"""Deterministic, non-executing multi-agent work planner."""

from dataclasses import dataclass

from applications.storeguard.store_network import StoreNetwork
from applications.storeguard.threat_evaluation import (
    WeatherThreat,
    ThreatAssessment,
    evaluate_threat,
)
from policy.storeguard_actions import (
    StoreGuardAction,
    WEATHER_RESPONSE_AGENT,
)

SRE_AGENT = "sre-troubleshooting-agent"


@dataclass(frozen=True)
class AgentWorkItem:
    threat_id: str
    store_id: str
    agent_name: str
    action: str
    status: str = "PLANNED"


@dataclass(frozen=True)
class MultiAgentPlan:
    assessment: ThreatAssessment
    work_items: tuple[AgentWorkItem, ...]


def plan_weather_response(
    network: StoreNetwork,
    threat: WeatherThreat,
) -> MultiAgentPlan:
    """Create store-scoped assignments without executing agents."""
    assessment = evaluate_threat(network, threat)
    items = []

    for store_id in assessment.affected_store_ids:
        items.append(AgentWorkItem(
            threat_id=threat.threat_id,
            store_id=store_id,
            agent_name=WEATHER_RESPONSE_AGENT,
            action=StoreGuardAction.ASSESS_WEATHER.value,
        ))
        items.append(AgentWorkItem(
            threat_id=threat.threat_id,
            store_id=store_id,
            agent_name=SRE_AGENT,
            action="investigate_store",
        ))

    return MultiAgentPlan(
        assessment=assessment,
        work_items=tuple(items),
    )
