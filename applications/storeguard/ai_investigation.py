"""Read-only, incident-scoped AI investigation inputs for StoreGuard demonstrations.

Never authorizes a transition. The worker receives an immutable snapshot, not a
Streamlit session, controller, or live mutable store.
"""
from dataclasses import dataclass
from applications.storeguard.recovery_agent import SystemHealth
from applications.storeguard.scenario_integration import SCENARIO_HEALTH


@dataclass(frozen=True)
class InvestigationSnapshot:
    incident_id: str
    store_id: str
    evidence_revision: int
    phase: str
    evidence_key: str
    elapsed_minutes: int
    controller_state: str
    health: SystemHealth

    @property
    def signature(self):
        return (self.incident_id, self.store_id, self.evidence_revision,
                self.phase, self.evidence_key, self.elapsed_minutes, self.controller_state)


def snapshot_for_phase(*, incident_id, store_id, evidence_revision, phase, controller_state):
    """Capture deterministic simulated evidence at the given scenario phase."""
    phase_name = getattr(phase, 'name', str(phase)).upper()
    if phase_name in ('MAINTENANCE', 'DIAGNOSTICS'):
        key, minutes = 'initial_outage', 10
    elif phase_name == 'PARTIAL_RESTORATION':
        key, minutes = 'partial_restoration', 15
    elif phase_name == 'ESCALATED':
        key, minutes = 'initial_outage', 30
    elif phase_name in ('FINAL_CHECK', 'AWAITING_APPROVAL'):
        key, minutes = 'services_restored', 20
    else:
        raise ValueError(f'No recovery evidence for phase {phase_name}')
    # Reconstruct rather than share the global mutable Pydantic fixture.
    health = SystemHealth(**SCENARIO_HEALTH[key].model_dump())
    return InvestigationSnapshot(str(incident_id), str(store_id), int(evidence_revision),
                                 phase_name, key, minutes, str(controller_state).upper(), health)


def executive_question(snapshot):
    """Constrain model claims to the observed snapshot and authoritative mode."""
    return (
        'Prepare a concise executive incident assessment (maximum 160 words) with '
        'headings: Business impact, Evidence, Recommendation, Human action. '
        f'This is SIMULATED evidence for incident {snapshot.incident_id}, '
        f'store {snapshot.store_id}, phase {snapshot.phase}. '
        f'The authoritative controller state is {snapshot.controller_state}. '
        'Do not infer that business operations have resumed from healthy diagnostics. '
        'If the controller is in MAINTENANCE, explicitly say normal operations are '
        'NOT authorized, even if every diagnostic is healthy. '
        'Distinguish measured simulated health from assumptions; do not claim live telemetry. '
        'The AI is read-only: it must not approve recovery, change store state, '
        'or imply that IBM Verify or Vault enforcement is connected.'
    )
