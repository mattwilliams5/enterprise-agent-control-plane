"""StoreGuard Weather Intelligence multi-store authorization."""

from dataclasses import dataclass

from applications.storeguard.threat_evaluation import ThreatAssessment
from policy.agent_capabilities import is_capability_declared
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT
from registry.registry import get_agent_record


@dataclass(frozen=True)
class WeatherAuthorizationDecision:
    authorized: bool
    reason: str
    store_ids: tuple[str, ...]


def authorize_weather_assessment(
    *,
    agent_name: str,
    assessment: ThreatAssessment,
    incident_id: str,
    allowed_store_ids: frozenset[str],
) -> WeatherAuthorizationDecision:
    """Fail closed unless every affected store is authorized."""

    denied = WeatherAuthorizationDecision(
        authorized=False,
        reason="Weather assessment authorization denied",
        store_ids=(),
    )

    if agent_name != WEATHER_RESPONSE_AGENT:
        return denied

    record = get_agent_record(agent_name)
    if (
        record is None
        or not record.approved
        or record.status != "active"
        or not record.vault_entity_id
    ):
        return denied

    if not is_capability_declared(agent_name, "assess_weather"):
        return denied

    if not isinstance(assessment, ThreatAssessment):
        return denied

    if not isinstance(incident_id, str) or not incident_id.strip():
        return denied

    if not isinstance(assessment.threat_id, str) or not assessment.threat_id.strip():
        return denied

    stores = assessment.affected_store_ids

    if not stores or len(stores) != len(set(stores)):
        return denied

    if any(not isinstance(store, str) or not store.strip() for store in stores):
        return denied

    if not isinstance(allowed_store_ids, frozenset):
        return denied

    if not set(stores).issubset(allowed_store_ids):
        return denied

    return WeatherAuthorizationDecision(
        authorized=True,
        reason="Weather assessment scope authorized",
        store_ids=tuple(stores),
    )
