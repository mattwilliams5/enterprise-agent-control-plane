"""Trusted read-only handlers for StoreGuard weather exercises.

Weather is simulated; AI inference is real when invoked with a live client.
No operational state changes or fabricated health observations.
"""
from applications.storeguard.threat_evaluation import ThreatAssessment
from applications.storeguard.weather_intelligence_agent import analyze_weather_threat


def build_live_handlers(*, network, assessment, client, model):
    if not isinstance(assessment, ThreatAssessment):
        raise TypeError("Trusted ThreatAssessment required")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Explicit AI model required")
    if client is None:
        raise ValueError("AI client required")

    affected = frozenset(assessment.affected_store_ids)

    def validate(intent, expected_action):
        if intent.action != expected_action:
            raise PermissionError("Wrong action")
        if intent.incident_id != assessment.threat_id:
            raise PermissionError("Incident mismatch")
        if intent.store_id not in affected:
            raise PermissionError("Store outside threat scope")
        store = network.get(intent.store_id)
        if store is None:
            raise PermissionError("Unknown store")
        return store

    def assess_weather(intent):
        store = validate(intent, "assess_weather")

        # Scope real AI inference to the single authorized store.
        scoped = ThreatAssessment(
            threat_id=assessment.threat_id,
            evaluated_count=1,
            affected_store_ids=(store.store_id,),
            unaffected_store_ids=(),
        )

        response = analyze_weather_threat(
            scoped,
            model=model,
            client=client,
        )

        return {
            "agent": intent.agent_id,
            "incident_id": assessment.threat_id,
            "store_id": store.store_id,
            "execution": "live_ai_inference",
            "weather_source": "fictional_deterministic_simulation",
            "report": response.report.model_dump(mode="json"),
            "model": response.model,
        }

    def investigate_store(intent):
        store = validate(intent, "investigate_store")

        # No actual telemetry was supplied. Do not invent health.
        return {
            "agent": intent.agent_id,
            "incident_id": assessment.threat_id,
            "store_id": store.store_id,
            "execution": "live_deterministic_investigation",
            "store_name": store.name,
            "region": store.region,
            "weather_exposure": "POTENTIAL_EXPOSURE",
            "connectivity": "NOT_OBSERVED",
            "inventory": "NOT_OBSERVED",
            "payments": "NOT_OBSERVED",
            "recommendation": (
                "Inspect current store telemetry and confirm "
                "conditions before making operational changes."
            ),
            "requires_human_review": True,
        }

    return {
        "assess_weather": assess_weather,
        "investigate_store": investigate_store,
    }
