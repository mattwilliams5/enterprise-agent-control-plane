"""Demo-only recovery gate. NOT an authentication or authorization provider.

Only local deterministic scenario evidence is accepted. The demo grant is issued
by this simulation module and must never be used for production authorization.
"""
from dataclasses import dataclass
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError
from applications.storeguard.recovery_agent import SystemHealth, observe_recovery, RecoveryDecision

@dataclass(frozen=True)
class DemoApproval:
    incident_id: str
    store_id: str
    evidence_revision: int
    operator_label: str
    simulation_only: bool = True

def issue_demo_approval(scenario, incident_id: str, store_id: str, evidence_revision: int, *, operator_label: str) -> DemoApproval:
    if scenario.phase != Phase.AWAITING_APPROVAL or scenario.assessment != "READY_FOR_FINAL_CHECK":
        raise ScenarioError("Scenario is not ready for simulated approval")
    if str(store_id) != scenario.store_id or evidence_revision != scenario.evidence_revision:
        raise ScenarioError("Store or evidence mismatch")
    if not incident_id or not operator_label:
        raise ValueError("Incident and operator label required")
    return DemoApproval(str(incident_id), str(store_id), evidence_revision, operator_label)

def _validate(scenario, approval: DemoApproval, incident_id: str):
    if type(approval) is not DemoApproval or not approval.simulation_only:
        raise ScenarioError("Invalid simulation approval")
    if (approval.incident_id != str(incident_id) or approval.store_id != scenario.store_id
            or approval.evidence_revision != scenario.evidence_revision):
        raise ScenarioError("Approval is for a different incident, store, or evidence revision")

def execute_demo_approval(scenario, approval: DemoApproval, incident_id: str):
    _validate(scenario, approval, incident_id)
    if scenario.phase != Phase.AWAITING_APPROVAL:
        raise ScenarioError("Approval is not pending")
    # These booleans represent only the local simulation's preconditions.
    # They MUST NOT be interpreted as authenticated IBM Verify authorization.
    return scenario.approve_recovery(authorized=True, verified=True,
                                     evidence_revision=approval.evidence_revision)

def execute_post_recovery_checks(scenario, approval: DemoApproval, incident_id: str, fresh_health: SystemHealth):
    _validate(scenario, approval, incident_id)
    if scenario.phase != Phase.RECOVERY:
        raise ScenarioError("Store is not in RECOVERY")
    if type(fresh_health) is not SystemHealth:
        raise ValueError("Fresh SystemHealth evidence required")
    observation = observe_recovery(fresh_health, elapsed_minutes=20, rto_minutes=30)
    if observation.decision != RecoveryDecision.READY_FOR_FINAL_CHECK:
        raise ScenarioError("Post-recovery health checks did not pass")
    return scenario.complete_recovery(post_checks_passed=True,
                                      evidence_revision=approval.evidence_revision)
