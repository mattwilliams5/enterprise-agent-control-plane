from enum import Enum
from pydantic import BaseModel


class RecoveryDecision(str, Enum):
    WAIT = "wait"
    READY_FOR_FINAL_CHECK = "ready_for_final_check"
    ESCALATE = "escalate"

class SystemHealth(BaseModel):
    connectivity: bool
    inventory: bool
    payments: bool
    safety: bool
    orders: bool

class RecoveryObservation(BaseModel):
    decision: RecoveryDecision
    unhealthy_systems: list[str]
    elapsed_minutes: int
    remaining_rto_minutes: int

def evaluate_recovery_readiness(
    health: SystemHealth,
    elapsed_minutes: int,
    rto_minutes: int,
) -> RecoveryDecision:

    if elapsed_minutes >= rto_minutes:
        return RecoveryDecision.ESCALATE

    elif all([
        health.connectivity,
        health.inventory,
        health.payments,
        health.safety,
        health.orders,
    ]):
        return RecoveryDecision.READY_FOR_FINAL_CHECK

    else:
        return RecoveryDecision.WAIT

def get_unhealthy_systems(health: SystemHealth) -> list[str]:
    """Return the names of required systems that are unhealthy."""
    systems = health.model_dump()

    return [
        name
        for name, is_healthy in systems.items()
        if not is_healthy
    ]


def observe_recovery(
    health: SystemHealth,
    elapsed_minutes: int,
    rto_minutes: int,
) -> RecoveryObservation:
    """Evaluate one recovery health observation."""

    if elapsed_minutes < 0 or rto_minutes <= 0:
        raise ValueError("Invalid recovery timing values")

    decision = evaluate_recovery_readiness(
        health,
        elapsed_minutes,
        rto_minutes,
    )

    return RecoveryObservation(
        decision=decision,
        unhealthy_systems=get_unhealthy_systems(health),
        elapsed_minutes=elapsed_minutes,
        remaining_rto_minutes=max(0, rto_minutes - elapsed_minutes),
    )


def monitor_recovery(
    health_readings: list[SystemHealth],
    rto_minutes: int,
    interval_minutes: int = 5,
) -> list[RecoveryObservation]:
    """Evaluate successive health readings until ready or escalated."""

    if rto_minutes <= 0 or interval_minutes <= 0:
        raise ValueError("RTO and interval must be positive")

    observations = []

    for index, health in enumerate(health_readings):
        elapsed_minutes = index * interval_minutes

        observation = observe_recovery(
            health=health,
            elapsed_minutes=elapsed_minutes,
            rto_minutes=rto_minutes,
        )

        observations.append(observation)

        if observation.decision != RecoveryDecision.WAIT:
            break

    return observations


def verify_final_recovery(
    monitoring_result: RecoveryObservation,
    fresh_health: SystemHealth,
    elapsed_minutes: int,
    rto_minutes: int,
) -> bool:
    """Verify recovery using a separate, fresh health reading."""

    if monitoring_result.decision != RecoveryDecision.READY_FOR_FINAL_CHECK:
        return False

    final_observation = observe_recovery(
        health=fresh_health,
        elapsed_minutes=elapsed_minutes,
        rto_minutes=rto_minutes,
    )

    return (
        final_observation.decision
        == RecoveryDecision.READY_FOR_FINAL_CHECK
    )
