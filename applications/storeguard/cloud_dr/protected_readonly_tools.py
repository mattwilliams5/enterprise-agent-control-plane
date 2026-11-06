"""Local-only Vault-governed, read-only StoreGuard tool execution boundary.

New Vault authentication and per-action authorization are required on every call.
No state-changing tools, cached authorizations, or production claims.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from applications.storeguard.cloud_dr.agent_execution_gate import AgentDenied
from applications.storeguard.cloud_dr.vault_agent_adapters import (
    ExistingRegistryAdapter, ScopedReadOnlyAuthorizer, VaultSessionVerifier,
)
from applications.storeguard.cloud_dr.agent_execution_gate import AgentExecutionGate
from identity.vault_identity import managed_approle_session


class ToolDenied(PermissionError):
    pass


# Deliberately no state-changing actions. Independently reviewed tool handlers
# must be explicitly registered by the trusted backend, never by the agent.
READ_ONLY_TOOL_ACTIONS = frozenset({'assess_weather', 'recommend_protection', 'investigate_store'})


class SqliteToolAudit:
    """Append-only *local demo* audit. Not appropriate for Cloud Run replicas."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS protected_tool_events (
                event_id TEXT PRIMARY KEY, action_run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, event_type TEXT NOT NULL,
                agent_id TEXT NOT NULL, incident_id TEXT NOT NULL,
                store_id TEXT NOT NULL, action TEXT NOT NULL,
                reason TEXT NOT NULL
            )''')

    def append(self, *, action_run_id, event_type, intent, reason):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute('''INSERT INTO protected_tool_events VALUES (?,?,?,?,?,?,?,?,?)''', (
                uuid4().hex, action_run_id, datetime.now(timezone.utc).isoformat(),
                event_type, intent.agent_id, intent.incident_id, intent.store_id,
                intent.action, reason,
            ))


class ProtectedReadOnlyRunner:
    """Enforce fresh login and authorization at the tool boundary.

    `secret_id_supplier` must be a trusted backend callable returning a *fresh*
    SecretID per invocation; no secrets may be passed by the agent or logged.
    `handlers` is a trusted allowlist and must contain only non-side-effecting
    callables that take (intent) and return a result.

    A successful tool invocation is not a blanket authorization of future calls.
    """

    def __init__(self, *, audit, decision_audit, delegation_check, scope_check,
                 handlers, session_factory=None):
        self.audit = audit
        self.handlers = dict(handlers)
        if not self.handlers or not set(self.handlers).issubset(READ_ONLY_TOOL_ACTIONS):
            raise ValueError('Only explicitly allowlisted read-only tool actions are supported')
        if not all(callable(f) for f in self.handlers.values()):
            raise TypeError('Tool handlers must be callable')
        self.session_factory = session_factory or managed_approle_session
        self.gate = AgentExecutionGate(
            identity=VaultSessionVerifier(),
            registry=ExistingRegistryAdapter(),
            authorizer=ScopedReadOnlyAuthorizer(
                delegation_check=delegation_check, scope_check=scope_check,
            ),
            audit=decision_audit,
        )

    def execute(self, *, intent, vault_addr, role_id, secret_id_supplier,
                required_policy='storeguard-investigator'):
        action_run_id = uuid4().hex
        if (intent.action not in self.handlers or
                intent.action not in READ_ONLY_TOOL_ACTIONS):
            self.audit.append(action_run_id=action_run_id, event_type='DENIED',
                              intent=intent, reason='tool_not_allowlisted')
            raise ToolDenied('Tool action not allowlisted')
        if not callable(secret_id_supplier):
            self.audit.append(action_run_id=action_run_id, event_type='DENIED',
                              intent=intent, reason='missing_trusted_credential_supplier')
            raise ToolDenied('Trusted credential supplier required')
        try:
            # The trusted supplier creates a new credential for EVERY tool call.
            secret_id = secret_id_supplier()
            if not isinstance(secret_id, str) or not secret_id:
                raise ValueError('No fresh SecretID available')
            with self.session_factory(
                vault_addr=vault_addr, role_id=role_id, secret_id=secret_id,
                required_policy=required_policy,
            ) as identity:
                # New run ID, fresh identity verification, registry check,
                # delegation/scope decision and durable pre-allow audit.
                self.gate.authorize_run(intent, evidence=(identity, intent.agent_id))
                # A separate, immediately-before-execution authorization decision
                # prevents reusing a prior run's authorization at this boundary.
                self.gate.authorize_run(intent, evidence=(identity, intent.agent_id))
                self.audit.append(action_run_id=action_run_id,
                                  event_type='STARTED', intent=intent, reason='allowed')
                try:
                    result = self.handlers[intent.action](intent)
                except Exception:
                    self.audit.append(action_run_id=action_run_id,
                                      event_type='FAILED', intent=intent,
                                      reason='tool_execution_failed')
                    raise
                self.audit.append(action_run_id=action_run_id,
                                  event_type='COMPLETED', intent=intent, reason='success')
            # Return only after session cleanup/revocation succeeded.
            return {'action_run_id': action_run_id, 'result': result}
        except Exception:
            # This may follow a STARTED/COMPLETED event if token cleanup fails;
            # those events truthfully describe the action, not final authorization.
            self.audit.append(action_run_id=action_run_id,
                              event_type='DENIED_OR_UNCONFIRMED', intent=intent,
                              reason='authentication_authorization_execution_or_cleanup_failed')
            raise
