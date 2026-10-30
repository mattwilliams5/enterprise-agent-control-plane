"""Integration checks against the real StoreGuard controller and recovery evaluator."""

import pytest

from applications.storeguard.controller import StoreGuardController
from applications.storeguard.scenario_integration import build_local_scenario
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError
from applications.storeguard.state_machine import StoreState


def make_scenario(path="successful_recovery"):
    controller = StoreGuardController()
    controller.register_store("1847")
    return controller, build_local_scenario(controller, "1847", path=path)


def advance_until_blocked(scenario):
    for _ in range(12):
        if scenario.tick() is None:
            return
    pytest.fail("Scenario failed to reach a blocking state")


def test_successful_scenario_reaches_approval_without_entering_recovery():
    controller, scenario = make_scenario()
    advance_until_blocked(scenario)
    assert scenario.phase == Phase.AWAITING_APPROVAL
    assert scenario.assessment == "READY_FOR_FINAL_CHECK"
    assert controller.stores["1847"].state == StoreState.MAINTENANCE
    assert scenario.evidence_revision == 3


def test_rto_breach_escalates_without_recovery_transition():
    controller, scenario = make_scenario("rto_breach")
    advance_until_blocked(scenario)
    assert scenario.phase == Phase.ESCALATED
    assert scenario.assessment == "ESCALATE"
    assert controller.stores["1847"].state == StoreState.MAINTENANCE


def test_unregistered_store_rejected():
    with pytest.raises(ValueError, match="registered"):
        build_local_scenario(StoreGuardController(), "1847")


def test_stale_approval_cannot_change_controller_state():
    controller, scenario = make_scenario()
    advance_until_blocked(scenario)
    with pytest.raises(ScenarioError, match="stale"):
        scenario.approve_recovery(
            authorized=True, verified=True,
            evidence_revision=scenario.evidence_revision - 1,
        )
    assert controller.stores["1847"].state == StoreState.MAINTENANCE
