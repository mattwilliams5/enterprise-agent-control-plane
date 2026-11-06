"""Fail-closed per-run agent gate; injectable trust/authorization/audit adapters.

This does NOT claim Vault integration until real Vault adapters are supplied,
verified, and tested. Identity evidence must be freshly verified every run.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from typing import Protocol


class AgentDenied(Exception):
    def __init__(self, run_id: str, reason: str):
        self.run_id, self.reason = run_id, reason
        super().__init__(f'{run_id}: {reason}')


@dataclass(frozen=True)
class AgentIntent:
    agent_id: str
    incident_id: str
    store_id: str
    action: str
    delegation_id: str


@dataclass(frozen=True)
class VerifiedAgent:
    agent_id: str
    workload_subject: str
    evidence_id: str


class IdentityVerifier(Protocol):
    def verify_fresh(self, evidence: object, *, run_id: str) -> VerifiedAgent: ...


class Registry(Protocol):
    def is_active(self, agent_id: str) -> bool: ...


class Authorizer(Protocol):
    def authorize(self, *, identity: VerifiedAgent, intent: AgentIntent,
                  run_id: str) -> bool: ...


class Audit(Protocol):
    def append(self, record: dict) -> None: ...


class AgentExecutionGate:
    def __init__(self, *, identity: IdentityVerifier, registry: Registry,
                 authorizer: Authorizer, audit: Audit):
        self.identity, self.registry = identity, registry
        self.authorizer, self.audit = authorizer, audit

    def authorize_run(self, intent: AgentIntent, evidence: object) -> str:
        """Reverify identity, registration, revocation and scope for EACH run.

        This function authorizes one run, not future tool actions. Protected
        tools MUST re-check authorization and revocation at execution time.
        A caller must not use this result as a cached future permission.
        """
        run_id = uuid4().hex
        verified = None
        decision, reason = 'deny', 'verification_failed'
        try:
            verified = self.identity.verify_fresh(evidence, run_id=run_id)
            if verified.agent_id != intent.agent_id:
                reason = 'identity_mismatch'
            elif not self.registry.is_active(verified.agent_id):
                reason = 'inactive_or_revoked'
            elif not self.authorizer.authorize(identity=verified, intent=intent, run_id=run_id):
                reason = 'scope_denied'
            else:
                decision, reason = 'allow', 'authorized'
        except Exception:
            # Fail closed, audit the denial, preserve no untrusted exception data.
            decision, reason = 'deny', 'verification_or_policy_error'
        record = {
            'run_id': run_id, 'agent_id': intent.agent_id,
            'incident_id': intent.incident_id, 'store_id': intent.store_id,
            'action': intent.action, 'delegation_id': intent.delegation_id,
            'verified_subject': verified.workload_subject if verified else None,
            'evidence_id': verified.evidence_id if verified else None,
            'decision': decision, 'reason': reason,
        }
        try:
            self.audit.append(record)  # Must be durable before an allow is returned.
        except Exception as exc:
            raise AgentDenied(run_id, 'audit_unavailable') from exc
        if decision != 'allow':
            raise AgentDenied(run_id, reason)
        return run_id
