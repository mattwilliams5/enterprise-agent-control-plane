"""One-trigger StoreGuard backend integration, without simulated approvals.

Trusted caller supplies the REAL governed runner, signed order submission,
and durable evidence writer. Only SG-002 has an authorized demonstration
weather/SRE delegation in the currently provisioned cloud environment.
The other five stores are shown as exposure candidates, never as executed.
"""
from __future__ import annotations

from uuid import uuid4

from applications.storeguard.cloud_dr.agent_execution_gate import AgentIntent
from applications.storeguard.store_network import build_demo_network
from applications.storeguard.threat_evaluation import WeatherThreat, evaluate_threat


INCIDENT = "DEMO-OKC-001"
WEATHER_AGENT = "storeguard-weather-response-agent"
SRE_AGENT = "sre-troubleshooting-agent"
WEATHER_DELEGATION = "demo-okc-001-sg-002-weather"
SRE_DELEGATION = "demo-okc-001-sg-002-sre"


def execute_demo(*, governed_runner, evidence_factory, submit_order,
                 persist_event, store_id="SG-002", transaction_store_id="1802"):
    """Execute two newly authorized read-only agent actions, then real DR test.

    No transition to maintenance/recovery/normal is performed or approved.
    The simulated primary outage only affects the test client's routing.
    A failing governance stage prevents the following stages entirely.
    """
    if store_id != "SG-002":
        raise ValueError("Only SG-002 has scoped demo delegations")
    if transaction_store_id != "1802":
        raise ValueError("Only enrolled transaction client 1802 is approved for this demo")
    if not all(callable(fn) for fn in (evidence_factory, submit_order, persist_event)):
        raise TypeError("Trusted execution dependencies required")

    network = build_demo_network()
    assessment = evaluate_threat(network, WeatherThreat(INCIDENT, 35.4676, -97.5164, 15))
    if store_id not in assessment.affected_store_ids or len(assessment.affected_store_ids) != 6:
        raise RuntimeError("Unexpected simulated exposure scope")

    demo_run_id = uuid4().hex
    exposed = list(assessment.affected_store_ids)
    persist_event(demo_run_id, "THREAT_ASSESSED", {
        "incident_id": INCIDENT, "weather_source": "fictional_deterministic_simulation",
        "stores_evaluated": assessment.evaluated_count, "exposed_store_ids": exposed,
        "protected_store_count": 0,
    })
    agent_evidence = {}
    for agent, action, delegation in (
        (WEATHER_AGENT, "assess_weather", WEATHER_DELEGATION),
        (SRE_AGENT, "investigate_store", SRE_DELEGATION),
    ):
        intent = AgentIntent(agent_id=agent, incident_id=INCIDENT,
                             store_id=store_id, action=action, delegation_id=delegation)
        # The real runner performs a NEW workload verification and policy decision
        # for the action, and another gate immediately before handler invocation.
        execution = governed_runner.execute(intent=intent, evidence=evidence_factory(intent))
        result = execution["result"]
        if not isinstance(result, dict) or result.get("store_id") != store_id:
            raise RuntimeError("Agent output does not match authorized store")
        if action == "assess_weather":
            report = result.get("report") or {}
            if (result.get("weather_source") != "fictional_deterministic_simulation"
                or report.get("requires_human_review") is not True
                or [s.get("store_id") for s in report.get("store_assessments", [])] != [store_id]):
                raise RuntimeError("Weather result failed mandatory checks")
        if action == "investigate_store" and result.get("requires_human_review") is not True:
            raise RuntimeError("SRE result must require human review")
        agent_evidence[action] = {
            "agent_id": agent,
            "action_run_id": execution["action_run_id"],
            "authorization_run_id": execution["authorization_run_id"],
            "action_gate_run_id": execution["action_gate_run_id"],
        }
        persist_event(demo_run_id, "AGENT_COMPLETED", {
            **agent_evidence[action], "action": action, "store_id": store_id,
            "result": result,
        })

    # The trusted callback MUST use private Cloud Run OIDC and Ed25519 headers;
    # do not accept a browser-supplied success status or fabricated receipt.
    order = submit_order(demo_run_id)
    if (not isinstance(order, dict) or order.get("outcome") != "acknowledged"
        or order.get("region") != "recovery"
        or order.get("store_id") != transaction_store_id
        or not isinstance(order.get("receipt_id"), str) or not order["receipt_id"]):
        persist_event(demo_run_id, "DR_NOT_VERIFIED", {
            "incident_id": INCIDENT, "store_id": store_id,
            "outcome": order.get("outcome") if isinstance(order, dict) else "unknown",
        })
        raise RuntimeError("Recovery region did not acknowledge a verified signed order")

    persist_event(demo_run_id, "DR_RECEIPT_VERIFIED", {
        "incident_id": INCIDENT, "store_id": store_id,
        "transaction_store_id": transaction_store_id,
        "order": order, "status": "recovery_transaction_verified",
        "store_recovery_approved": False,
    })
    return {
        "demo_run_id": demo_run_id,
        "incident_id": INCIDENT,
        "exposed_store_ids": exposed,
        "governed_store_ids": [store_id],
        "transaction_store_id": transaction_store_id,
        "remaining_store_ids": [s for s in exposed if s != store_id],
        "agent_evidence": agent_evidence,
        "order": order,
        "status": "recovery_transaction_verified__store_recovery_not_approved",
    }
