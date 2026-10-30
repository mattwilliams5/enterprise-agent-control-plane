"""Connect the deterministic demo scenario to StoreGuard's real local controller.

This adapter is NOT an identity provider, approval service, or live monitoring.
Do not pass browser-controlled approval booleans to TornadoScenario.approve_recovery.
"""

from applications.storeguard.controller import StoreGuardController
from applications.storeguard.recovery_agent import (
    SystemHealth,
    observe_recovery,
)
from applications.storeguard.scenario_orchestrator import TornadoScenario
from applications.storeguard.state_machine import StoreState

SCENARIO_HEALTH = {
    "initial_outage": SystemHealth(
        connectivity=False, inventory=False, payments=True, safety=True, orders=True
    ),
    "partial_restoration": SystemHealth(
        connectivity=True, inventory=False, payments=True, safety=True, orders=True
    ),
    "services_restored": SystemHealth(
        connectivity=True, inventory=True, payments=True, safety=True, orders=True
    ),
}


def build_local_scenario(
    controller: StoreGuardController,
    store_id: str,
    *,
    path: str = "successful_recovery",
    rto_minutes: int = 30,
) -> TornadoScenario:
    """Bind an already-registered store to authoritative local transitions.

    The scenario's approval method remains a demonstration contract only.
    Production recovery must use backend-authenticated approval and fresh evidence.
    """
    if rto_minutes <= 0:
        raise ValueError("RTO must be positive")
    store_id = str(store_id)
    if store_id not in controller.stores:
        raise ValueError(f"Store {store_id} must be registered before orchestration")

    def transition(requested_store: str, target: str) -> bool:
        if requested_store != store_id:
            return False
        try:
            target_state = StoreState[target.upper()]
        except KeyError:
            return False
        return controller.request_transition(requested_store, target_state)

    def assess(scenario_name: str, elapsed_minutes: int) -> str:
        health = SCENARIO_HEALTH[scenario_name]
        observation = observe_recovery(health, elapsed_minutes, rto_minutes)
        return observation.decision.name

    return TornadoScenario(store_id, transition, assess, path=path)
