"""Deterministic, UI-independent StoreGuard incident demonstration orchestration.

No LLM or UI may approve recovery. This module never invokes a production
state transition itself; the caller must use the existing StoreGuardController.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Phase(str, Enum):
    IDLE = "idle"
    WEATHER_ALERT = "weather_alert"
    PROTECTED = "protected"
    MAINTENANCE = "maintenance"
    DIAGNOSTICS = "diagnostics"
    PARTIAL_RESTORATION = "partial_restoration"
    FINAL_CHECK = "final_check"
    AWAITING_APPROVAL = "awaiting_approval"
    ESCALATED = "escalated"
    RECOVERY = "recovery"
    NORMAL = "normal"


class ScenarioError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScenarioEvent:
    sequence: int
    phase: Phase
    description: str


@dataclass
class TornadoScenario:
    """Advance exactly one event per tick. Never self-approve recovery.

    `transition` must call the authoritative controller and return its result.
    `assess` must call the deterministic recovery evaluator and return its
    decision value (WAIT, READY_FOR_FINAL_CHECK, or ESCALATE).
    """
    store_id: str
    transition: Callable[[str, str], bool]
    assess: Callable[[str, int], str]
    path: str = "successful_recovery"
    phase: Phase = Phase.IDLE
    paused: bool = False
    events: list[ScenarioEvent] = field(default_factory=list)
    assessment: str | None = None
    evidence_revision: int = 0
    approved_revision: int | None = None

    def __post_init__(self):
        if self.path not in ("successful_recovery", "rto_breach"):
            raise ValueError("Unsupported scenario path")
        self.store_id = str(self.store_id)

    def _record(self, phase: Phase, description: str) -> ScenarioEvent:
        self.phase = phase
        event = ScenarioEvent(len(self.events) + 1, phase, description)
        self.events.append(event)
        return event

    def _transition(self, target: str):
        if not self.transition(self.store_id, target):
            raise ScenarioError(f"Controller denied {target} for {self.store_id}")

    def tick(self) -> ScenarioEvent | None:
        """Progress one step. Stop at approval or escalation."""
        if self.paused or self.phase in (Phase.AWAITING_APPROVAL, Phase.ESCALATED, Phase.NORMAL):
            return None
        if self.phase == Phase.IDLE:
            return self._record(Phase.WEATHER_ALERT, "Simulated tornado alert received")
        if self.phase == Phase.WEATHER_ALERT:
            self._transition("protected")
            return self._record(Phase.PROTECTED, "Controller approved PROTECTED")
        if self.phase == Phase.PROTECTED:
            self._transition("maintenance")
            return self._record(Phase.MAINTENANCE, "Connectivity lost; controller approved MAINTENANCE")
        if self.phase == Phase.MAINTENANCE:
            self.assessment = self.assess("initial_outage", 10)
            if self.assessment != "WAIT":
                raise ScenarioError("Unexpected initial assessment")
            self.evidence_revision += 1
            return self._record(Phase.DIAGNOSTICS, "Initial outage: WAIT")
        if self.phase == Phase.DIAGNOSTICS:
            if self.path == "rto_breach":
                self.assessment = self.assess("initial_outage", 30)
                if self.assessment != "ESCALATE":
                    raise ScenarioError("Expected ESCALATE at RTO")
                self.evidence_revision += 1
                return self._record(Phase.ESCALATED, "RTO reached: human escalation required")
            self.assessment = self.assess("partial_restoration", 15)
            if self.assessment != "WAIT":
                raise ScenarioError("Expected WAIT during partial restoration")
            self.evidence_revision += 1
            return self._record(Phase.PARTIAL_RESTORATION, "Connectivity restored; inventory unhealthy: WAIT")
        if self.phase == Phase.PARTIAL_RESTORATION:
            self.assessment = self.assess("services_restored", 20)
            if self.assessment != "READY_FOR_FINAL_CHECK":
                raise ScenarioError("Expected final-check readiness")
            self.evidence_revision += 1
            return self._record(Phase.FINAL_CHECK, "Diagnostics healthy; final verification required")
        if self.phase == Phase.FINAL_CHECK:
            return self._record(Phase.AWAITING_APPROVAL, "Paused for authenticated human verification and approval")
        raise ScenarioError(f"Unsupported phase: {self.phase}")

    def approve_recovery(self, *, authorized: bool, verified: bool, evidence_revision: int):
        """Local contract only; production caller must validate identity and evidence.

        This function is NOT an authentication or authorization provider.
        The caller must obtain `authorized` from a trusted backend, never
        directly from a browser checkbox or LLM output.
        """
        if self.phase != Phase.AWAITING_APPROVAL:
            raise ScenarioError("Recovery is not awaiting approval")
        if not authorized or not verified:
            raise ScenarioError("Human authorization and verification are required")
        if evidence_revision != self.evidence_revision:
            raise ScenarioError("Recovery evidence is stale")
        self._transition("recovery")
        self.approved_revision = evidence_revision
        return self._record(Phase.RECOVERY, "Authorized approval; controller entered RECOVERY")

    def complete_recovery(self, *, post_checks_passed: bool, evidence_revision: int):
        if self.phase != Phase.RECOVERY or self.approved_revision is None:
            raise ScenarioError("No approved recovery in progress")
        if evidence_revision != self.approved_revision or evidence_revision != self.evidence_revision:
            raise ScenarioError("Recovery approval/evidence is stale")
        if not post_checks_passed:
            raise ScenarioError("Post-recovery checks failed; remain in RECOVERY")
        self._transition("normal")
        return self._record(Phase.NORMAL, "Post-recovery checks passed; controller entered NORMAL")

    def reset(self):
        """Reset orchestration only; caller must separately reset its controller."""
        self.phase = Phase.IDLE
        self.paused = False
        self.events.clear()
        self.assessment = None
        self.evidence_revision = 0
        self.approved_revision = None
