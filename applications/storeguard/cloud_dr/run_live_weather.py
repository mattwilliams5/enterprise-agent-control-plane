"""Execute one Vault-governed StoreGuard weather assessment in Cloud Run.

Fixed demonstration assignment. No caller-selected agent or permissions.
"""
import os

from openai import OpenAI

from google.cloud import firestore

from applications.storeguard.cloud_dr.agent_execution_gate import AgentIntent
from applications.storeguard.cloud_dr.live_agent_handlers import build_live_handlers
from applications.storeguard.cloud_dr.live_agent_permissions import build_permission_checks
from applications.storeguard.cloud_dr.live_agent_runner import build_live_runner
from applications.storeguard.store_network import build_demo_network
from applications.storeguard.threat_evaluation import WeatherThreat, evaluate_threat


PROJECT = "storeguard-dr-demo-2026"
DATABASE = "storeguard-executive-evidence"
AGENT = "storeguard-weather-response-agent"
INCIDENT = "DEMO-OKC-001"
STORE = "SG-002"
DELEGATION = "demo-okc-001-sg-002-weather"


def main():
    # Refuse execution outside the intended cloud job environment.
    if not os.environ.get("CLOUD_RUN_JOB"):
        raise RuntimeError("Cloud Run Job required")

    network = build_demo_network()
    assessment = evaluate_threat(
        network,
        WeatherThreat(INCIDENT, 35.4676, -97.5164, 15),
    )

    if STORE not in assessment.affected_store_ids:
        raise RuntimeError("Store not in incident exposure")

    db = firestore.Client(project=PROJECT, database=DATABASE)
    delegation_check, scope_check = build_permission_checks(client=db)

    handlers = build_live_handlers(
        network=network,
        assessment=assessment,
        client=OpenAI(),
        model="gpt-4.1-mini",
    )

    runner = build_live_runner(
        handlers={"assess_weather": handlers["assess_weather"]},
        delegation_check=delegation_check,
        scope_check=scope_check,
    )

    intent = AgentIntent(
        agent_id=AGENT,
        incident_id=INCIDENT,
        store_id=STORE,
        action="assess_weather",
        delegation_id=DELEGATION,
    )

    # Identity and assignment are selected by trusted backend code.
    # The runner performs fresh checks and persists decision/tool audits.
    execution = runner.execute(
        intent=intent,
        evidence=AGENT,
    )

    result = execution["result"]
    if (
        result["store_id"] != STORE
        or result["weather_source"] != "fictional_deterministic_simulation"
        or not result["report"]["requires_human_review"]
        or [s["store_id"] for s in result["report"]["store_assessments"]] != [STORE]
    ):
        raise RuntimeError("Invalid weather assessment")

    # Persist the actual read-only investigation result, not just an
    # authorization decision. Create-only; never overwrite evidence.
    db.collection("storeguard_agent_outcomes").document(
        execution["action_run_id"]
    ).create({
        "agent_id": AGENT,
        "incident_id": INCIDENT,
        "store_id": STORE,
        "action": intent.action,
        "authorization_run_id": execution["authorization_run_id"],
        "action_gate_run_id": execution["action_gate_run_id"],
        "result": result,
        "source": "live_governed_weather_intelligence",
    })

    print("PASS: Vault-governed Weather Intelligence completed")
    print("PASS: Authorization and tool events persisted")
    print("PASS: Weather assessment persisted")
    print("Store:", STORE)
    print("Action run ID:", execution["action_run_id"])


if __name__ == "__main__":
    main()
