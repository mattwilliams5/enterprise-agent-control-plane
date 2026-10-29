from applications.storeguard.recovery_agent import (
    SystemHealth,
    RecoveryDecision,
    RecoveryObservation,
    evaluate_recovery_readiness,
    get_unhealthy_systems,
    observe_recovery,
    monitor_recovery,
    verify_final_recovery,
)


def test_recovery_ready_when_all_systems_healthy():
    health = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=True,
        safety=True,
        orders=True,
    )

    decision = evaluate_recovery_readiness(
        health,
        elapsed_minutes=10,
        rto_minutes=30,
    )

    assert decision == RecoveryDecision.READY_FOR_FINAL_CHECK


def test_recovery_waits_when_inventory_unhealthy():
    health = SystemHealth(
        connectivity=True,
        inventory=False,
        payments=True,
        safety=True,
        orders=True,
    )

    decision = evaluate_recovery_readiness(
        health,
        elapsed_minutes=10,
        rto_minutes=30,
    )

    assert decision == RecoveryDecision.WAIT


def test_recovery_escalates_when_rto_exceeded():
    health = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=True,
        safety=True,
        orders=True,
    )

    decision = evaluate_recovery_readiness(
        health,
        elapsed_minutes=35,
        rto_minutes=30,
    )

    assert decision == RecoveryDecision.ESCALATE


def test_get_unhealthy_systems():
    health = SystemHealth(
        connectivity=True,
        inventory=False,
        payments=False,
        safety=True,
        orders=True,
    )

    result = get_unhealthy_systems(health)

    assert result == ["inventory", "payments"]


def test_recovery_observation_reports_unhealthy_systems():
    health = SystemHealth(
        connectivity=True,
        inventory=False,
        payments=True,
        safety=True,
        orders=True,
    )

    observation = observe_recovery(
        health,
        elapsed_minutes=10,
        rto_minutes=30,
    )

    assert observation.decision == RecoveryDecision.WAIT
    assert observation.unhealthy_systems == ["inventory"]
    assert observation.remaining_rto_minutes == 20


def test_monitor_recovery_waits_until_all_systems_healthy():
    readings = [
        SystemHealth(
            connectivity=True,
            inventory=False,
            payments=False,
            safety=True,
            orders=True,
        ),
        SystemHealth(
            connectivity=True,
            inventory=False,
            payments=True,
            safety=True,
            orders=True,
        ),
        SystemHealth(
            connectivity=True,
            inventory=True,
            payments=True,
            safety=True,
            orders=True,
        ),
    ]

    observations = monitor_recovery(
        health_readings=readings,
        rto_minutes=30,
        interval_minutes=5,
    )

    assert len(observations) == 3
    assert observations[0].decision == RecoveryDecision.WAIT
    assert observations[1].unhealthy_systems == ["inventory"]
    assert observations[2].decision == RecoveryDecision.READY_FOR_FINAL_CHECK
    assert observations[2].elapsed_minutes == 10


def test_monitor_recovery_escalates_at_rto():
    unhealthy = SystemHealth(
        connectivity=False,
        inventory=False,
        payments=True,
        safety=True,
        orders=True,
    )

    readings = [unhealthy] * 5

    observations = monitor_recovery(
        health_readings=readings,
        rto_minutes=15,
        interval_minutes=5,
    )

    assert len(observations) == 4
    assert observations[-1].decision == RecoveryDecision.ESCALATE
    assert observations[-1].elapsed_minutes == 15
    assert observations[-1].remaining_rto_minutes == 0
    assert observations[-1].unhealthy_systems == [
        "connectivity",
        "inventory",
    ]


def test_final_verification_blocks_recovery_when_payments_fail():
    healthy = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=True,
        safety=True,
        orders=True,
    )

    monitoring_result = observe_recovery(
        health=healthy,
        elapsed_minutes=10,
        rto_minutes=30,
    )

    fresh_health = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=False,
        safety=True,
        orders=True,
    )

    verified = verify_final_recovery(
        monitoring_result=monitoring_result,
        fresh_health=fresh_health,
        elapsed_minutes=15,
        rto_minutes=30,
    )

    assert verified is False


def test_final_verification_succeeds_when_systems_remain_healthy():
    healthy = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=True,
        safety=True,
        orders=True,
    )

    monitoring_result = observe_recovery(
        health=healthy,
        elapsed_minutes=10,
        rto_minutes=30,
    )

    verified = verify_final_recovery(
        monitoring_result=monitoring_result,
        fresh_health=healthy.model_copy(),
        elapsed_minutes=15,
        rto_minutes=30,
    )

    assert verified is True
