"""StoreGuard weather-to-agent execution integration.

The caller must provide a CloudGovernedReadOnlyRunner configured
with trusted, live identity, registry, authorization and audit adapters.
No simulated identity is created here.
"""
from __future__ import annotations

from dataclasses import dataclass

from applications.storeguard.cloud_dr.agent_execution_gate import AgentIntent
from applications.storeguard.multi_agent_planner import plan_weather_response


@dataclass(frozen=True)
class AgentExecutionResult:
    agent_id: str
    incident_id: str
    store_id: str
    action: str
    action_run_id: str
    authorization_run_id: str
    action_gate_run_id: str
    result: object


def execute_weather_response(
    *,
    network,
    threat,
    runner,
    evidence_factory,
    delegation_id,
):
    """Execute planned work using independent governed tool invocations.

    Evidence must originate from a trusted runtime, never an API caller.
    Authorization and audit enforcement belong to the governed runner.
    """
    if not callable(evidence_factory):
        raise TypeError("Trusted evidence_factory is required")
    if not isinstance(delegation_id, str) or not delegation_id.strip():
        raise ValueError("An explicit delegation ID is required")

    plan = plan_weather_response(network, threat)
    completed = []

    for item in plan.work_items:
        intent = AgentIntent(
            agent_id=item.agent_name,
            incident_id=item.threat_id,
            store_id=item.store_id,
            action=item.action,
            delegation_id=delegation_id,
        )

        # The runner independently verifies the identity and checks
        # registration, delegation, scope and revocation twice.
        # A denied action aborts the workflow rather than being hidden.
        execution = runner.execute(
            intent=intent,
            evidence=evidence_factory(intent),
        )

        completed.append(
            AgentExecutionResult(
                agent_id=intent.agent_id,
                incident_id=intent.incident_id,
                store_id=intent.store_id,
                action=intent.action,
                action_run_id=execution["action_run_id"],
                authorization_run_id=execution["authorization_run_id"],
                action_gate_run_id=execution["action_gate_run_id"],
                result=execution["result"],
            )
        )

    return plan, tuple(completed)
