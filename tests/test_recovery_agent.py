from applications.storeguard.recovery_agent import (
    SystemHealth,
    RecoveryDecision,
    evaluate_recovery_readiness,
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
