"""Fail-closed, read-only cloud execution orchestration.

The caller must supply trusted identity, registry, authorization and audit
adapters. This module does not authenticate HTTP callers or provision Vault
credentials. Those responsibilities belong to the eventual cloud runtime.
"""
from __future__ import annotations

from uuid import uuid4

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentExecutionGate,
)
from applications.storeguard.cloud_dr.protected_readonly_tools import (
    READ_ONLY_TOOL_ACTIONS,
    ToolDenied,
)


class CloudGovernedReadOnlyRunner:
    def __init__(
        self, *,
        identity_verifier,
        registry,
        authorizer,
        decision_audit,
        tool_audit,
        handlers,
    ):
        if not handlers or not set(handlers).issubset(READ_ONLY_TOOL_ACTIONS):
            raise ValueError("Only approved read-only actions are supported")

        if not all(callable(fn) for fn in handlers.values()):
            raise TypeError("Every tool handler must be callable")

        self.handlers = dict(handlers)
        self.tool_audit = tool_audit
        self.gate = AgentExecutionGate(
            identity=identity_verifier,
            registry=registry,
            authorizer=authorizer,
            audit=decision_audit,
        )

    def execute(self, *, intent, evidence):
        """Execute a trusted read-only tool after independent gate checks."""
        action_run_id = uuid4().hex

        def record(event_type, reason):
            self.tool_audit.append(
                action_run_id=action_run_id,
                event_type=event_type,
                intent=intent,
                reason=reason,
            )

        if intent.action not in self.handlers:
            record("DENIED", "tool_not_allowlisted")
            raise ToolDenied("Tool action not allowlisted")

        try:
            # New decision, fresh verification and shared-registry lookup.
            first_run_id = self.gate.authorize_run(intent, evidence)

            # Separate authorization immediately before the action.
            # This must invoke the trusted verifier again and reread
            # revocation/delegation/scope state.
            action_gate_run_id = self.gate.authorize_run(intent, evidence)

        except Exception:
            record("DENIED_OR_UNCONFIRMED", "authorization_failed")
            raise

        # A successful STARTED audit write is mandatory before invoking
        # the protected handler.
        record("STARTED", "allowed")

        try:
            result = self.handlers[intent.action](intent)
        except Exception:
            record("FAILED", "tool_execution_failed")
            raise

        # Do not return success if outcome persistence fails.
        record("COMPLETED", "success")

        return {
            "action_run_id": action_run_id,
            "authorization_run_id": first_run_id,
            "action_gate_run_id": action_gate_run_id,
            "result": result,
        }
