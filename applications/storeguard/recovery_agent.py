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