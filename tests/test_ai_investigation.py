import pytest
from applications.storeguard.ai_investigation import snapshot_for_phase, executive_question
from applications.storeguard.scenario_orchestrator import Phase


def snap(phase, revision=1):
    return snapshot_for_phase(incident_id='WX-1', store_id='1847',
        evidence_revision=revision, phase=phase, controller_state='MAINTENANCE')


def test_hard_down_uses_outage_evidence():
    s = snap(Phase.MAINTENANCE)
    assert s.evidence_key == 'initial_outage'
    assert not s.health.connectivity
    assert s.controller_state == 'MAINTENANCE'


def test_checkpoint_uses_restored_evidence_without_authorizing_operations():
    s = snap(Phase.AWAITING_APPROVAL, 3)
    assert s.evidence_key == 'services_restored'
    assert all(s.health.model_dump().values())
    assert 'NOT authorized' in executive_question(s)


def test_revision_changes_signature():
    assert snap(Phase.DIAGNOSTICS, 1).signature != snap(Phase.DIAGNOSTICS, 2).signature


def test_invalid_phase_is_rejected():
    with pytest.raises(ValueError):
        snap(Phase.IDLE)
