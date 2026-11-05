"""Opt-in Vault-backed adapters for the Batch 6B agent gate.

Local integration only. No side-effecting tools are called by this module.
Do not treat a run authorization as authorization for later tool calls.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from applications.storeguard.cloud_dr.agent_execution_gate import (
    AgentDenied, AgentExecutionGate, VerifiedAgent,
)
from identity.show_id import verify_agent_identity
from identity.vault_identity import managed_approle_session
from policy.agent_capabilities import is_capability_declared
from registry.registry import get_agent_record


class SqliteDecisionAudit:
    """Durable local audit; NOT a cross-region production audit service."""

    def __init__(self, db_path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS gate_decisions (
                run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                decision TEXT NOT NULL, record_json TEXT NOT NULL
            )""")

    def append(self, record):
        # Replacing records would allow rewriting authorization history.
        payload = json.dumps(record, sort_keys=True, separators=(',', ':'))
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute(
                'INSERT INTO gate_decisions VALUES (?, ?, ?, ?)',
                (record['run_id'], datetime.now(timezone.utc).isoformat(),
                 record['decision'], payload),
            )


class VaultSessionVerifier:
    def verify_fresh(self, evidence, *, run_id):
        """Only accepts an identity yielded by a fresh managed Vault login.

        The trusted executor, not the agent/caller, supplies evidence.
        """
        identity, agent_name = evidence
        verify_agent_identity(agent_name, identity)
        if not identity.entity_id or identity.token_ttl <= 0:
            raise ValueError('Vault identity missing or expired')
        # Login request IDs are issued by Vault; require one for traceability.
        if not identity.login_request_id:
            raise ValueError('Vault login request ID unavailable')
        return VerifiedAgent(
            agent_id=agent_name, workload_subject=identity.entity_id,
            evidence_id=identity.login_request_id,
        )


class ExistingRegistryAdapter:
    def is_active(self, agent_id):
        record = get_agent_record(agent_id)  # fresh lookup for every run
        return bool(record and record.approved and record.status == 'active'
                    and record.vault_entity_id)


class ScopedReadOnlyAuthorizer:
    """Require explicit trusted delegation and incident/store scope checks."""

    def __init__(self, *, delegation_check, scope_check):
        if not callable(delegation_check) or not callable(scope_check):
            raise TypeError('Trusted delegation and scope validators required')
        self.delegation_check = delegation_check
        self.scope_check = scope_check

    def authorize(self, *, identity, intent, run_id):
        record = get_agent_record(intent.agent_id)
        if not (record and record.approved and record.status == 'active'
                and record.vault_entity_id == identity.workload_subject):
            return False
        if not all(isinstance(v, str) and v.strip() for v in (
                intent.incident_id, intent.store_id, intent.action,
                intent.delegation_id)):
            return False
        if not is_capability_declared(intent.agent_id, intent.action):
            return False
        # No state changing actions are allowed by this adapter.
        # Require both callback decisions each run. Exceptions fail closed in gate.
        if not self.delegation_check(identity=identity, intent=intent, run_id=run_id):
            return False
        return self.scope_check(identity=identity, intent=intent, run_id=run_id) is True


class VaultRunAuthorizer:
    """Run-level authorization using trusted per-run Vault AppRole credentials.

    Does not invoke tools. It is unsafe to cache or reuse returned run IDs as
    authorization for subsequent actions; tools require independent enforcement.
    """

    def __init__(self, *, audit, delegation_check, scope_check):
        self.gate = AgentExecutionGate(
            identity=VaultSessionVerifier(), registry=ExistingRegistryAdapter(),
            authorizer=ScopedReadOnlyAuthorizer(
                delegation_check=delegation_check, scope_check=scope_check),
            audit=audit,
        )

    def authorize(self, *, intent, vault_addr, role_id, secret_id,
                  required_policy='storeguard-investigator'):
        # Managed context verifies a fresh Vault login and revokes the token.
        # Do not return a successful authorization if revocation fails.
        with managed_approle_session(
                vault_addr=vault_addr, role_id=role_id,
                secret_id=secret_id, required_policy=required_policy) as identity:
            return self.gate.authorize_run(
                intent, evidence=(identity, intent.agent_id))
