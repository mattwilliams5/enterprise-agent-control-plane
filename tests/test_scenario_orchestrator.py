import pytest
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError, TornadoScenario


def make_scenario(path="successful_recovery"):
    transitions = []
    decisions = {("initial_outage", 10): "WAIT", ("partial_restoration", 15): "WAIT", ("services_restored", 20): "READY_FOR_FINAL_CHECK", ("initial_outage", 30): "ESCALATE"}
    scenario = TornadoScenario("1847", lambda sid, target: transitions.append((sid, target)) or True, lambda name, elapsed: decisions[(name, elapsed)], path=path)
    return scenario, transitions


def run_until_stopped(scenario):
    for _ in range(12):
        if scenario.tick() is None:
            return
    raise AssertionError("Scenario did not stop")


def test_success_pauses_before_recovery():
    scenario, transitions = make_scenario()
    run_until_stopped(scenario)
    assert scenario.phase == Phase.AWAITING_APPROVAL
    assert transitions == [("1847", "protected"), ("1847", "maintenance")]
    assert scenario.assessment == "READY_FOR_FINAL_CHECK"


def test_approval_requires_authority_verification_and_fresh_evidence():
    scenario, transitions = make_scenario()
    run_until_stopped(scenario)
    for args in ({"authorized": False, "verified": True, "evidence_revision": 3}, {"authorized": True, "verified": False, "evidence_revision": 3}, {"authorized": True, "verified": True, "evidence_revision": 2}):
        with pytest.raises(ScenarioError):
            scenario.approve_recovery(**args)
    assert len(transitions) == 2
    scenario.approve_recovery(authorized=True, verified=True, evidence_revision=3)
    assert scenario.phase == Phase.RECOVERY
    with pytest.raises(ScenarioError):
        scenario.complete_recovery(post_checks_passed=False, evidence_revision=3)
    assert scenario.phase == Phase.RECOVERY
    scenario.complete_recovery(post_checks_passed=True, evidence_revision=3)
    assert scenario.phase == Phase.NORMAL


def test_rto_breach_never_requests_recovery():
    scenario, transitions = make_scenario("rto_breach")
    run_until_stopped(scenario)
    assert scenario.phase == Phase.ESCALATED
    assert len(transitions) == 2
    with pytest.raises(ScenarioError):
        scenario.approve_recovery(authorized=True, verified=True, evidence_revision=scenario.evidence_revision)


def test_pause_and_reset():
    scenario, transitions = make_scenario()
    scenario.paused = True
    assert scenario.tick() is None
    scenario.paused = False
    assert scenario.tick().phase == Phase.WEATHER_ALERT
    scenario.reset()
    assert scenario.phase == Phase.IDLE
    assert scenario.events == []
