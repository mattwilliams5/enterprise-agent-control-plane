import pytest
from applications.storeguard.controller import StoreGuardController
from applications.storeguard.scenario_integration import build_local_scenario, SCENARIO_HEALTH
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError
from applications.storeguard.state_machine import StoreState
from applications.storeguard.governed_recovery import (issue_demo_approval, execute_demo_approval, execute_post_recovery_checks)
from applications.storeguard.recovery_agent import SystemHealth

def ready(path="successful_recovery"):
    controller = StoreGuardController()
    controller.register_store("1847")
    scenario = build_local_scenario(controller, "1847", path=path)
    for _ in range(8):
        if scenario.tick() is None: break
    return controller, scenario

def test_simulated_approval_then_verified_normal():
    controller, scenario = ready()
    grant = issue_demo_approval(scenario, "WX-2026-001", "1847", scenario.evidence_revision, operator_label="Demo operator")
    execute_demo_approval(scenario, grant, "WX-2026-001")
    assert scenario.phase == Phase.RECOVERY
    assert controller.stores["1847"].state == StoreState.RECOVERY
    execute_post_recovery_checks(scenario, grant, "WX-2026-001", SCENARIO_HEALTH["services_restored"])
    assert scenario.phase == Phase.NORMAL
    assert controller.stores["1847"].state == StoreState.NORMAL

def test_wrong_incident_rejected():
    controller, scenario = ready()
    grant = issue_demo_approval(scenario, "WX-2026-001", "1847", scenario.evidence_revision, operator_label="Demo operator")
    with pytest.raises(ScenarioError, match="different incident"):
        execute_demo_approval(scenario, grant, "OTHER")
    assert controller.stores["1847"].state == StoreState.MAINTENANCE

def test_stale_evidence_rejected():
    controller, scenario = ready()
    with pytest.raises(ScenarioError, match="mismatch"):
        issue_demo_approval(scenario, "WX-2026-001", "1847", scenario.evidence_revision-1, operator_label="Demo operator")

def test_unhealthy_post_checks_cannot_turn_green():
    controller, scenario = ready()
    grant = issue_demo_approval(scenario, "WX-2026-001", "1847", scenario.evidence_revision, operator_label="Demo operator")
    execute_demo_approval(scenario, grant, "WX-2026-001")
    with pytest.raises(ScenarioError, match="did not pass"):
        execute_post_recovery_checks(scenario, grant, "WX-2026-001", SCENARIO_HEALTH["initial_outage"])
    assert scenario.phase == Phase.RECOVERY
    assert controller.stores["1847"].state == StoreState.RECOVERY

def test_rto_breach_cannot_be_approved():
    controller, scenario = ready("rto_breach")
    assert scenario.phase == Phase.ESCALATED
    with pytest.raises(ScenarioError, match="not ready"):
        issue_demo_approval(scenario, "WX-2026-001", "1847", scenario.evidence_revision, operator_label="Demo operator")
