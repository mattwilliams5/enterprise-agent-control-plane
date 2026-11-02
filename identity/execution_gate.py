"""StoreGuard execution authorization gate.

The trusted caller supplies fresh, single-use AppRole credentials.
Provisioner/root credentials must never enter this module.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from identity.show_id import verify_agent_identity
from identity.vault_identity import authenticate_approle
from policy.engine import authorize_investigation


class ExecutionDenied(PermissionError):
    pass


def _record(db_path, event):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS execution_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                store_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                action TEXT NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                vault_entity_id TEXT
            )
        """)
        db.execute("""
            INSERT INTO execution_events VALUES (
                :event_id, :run_id, :timestamp, :agent,
                :store_id, :incident_id, :action, :event_type,
                :reason, :vault_entity_id
            )
        """, event)


def _event(run_id, agent, store_id, incident_id, event_type,
           reason, vault_entity_id=None):
    return {
        "event_id": str(uuid.uuid4()),
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "store_id": store_id,
        "incident_id": incident_id,
        "action": "check_health",
        "event_type": event_type,
        "reason": reason,
        "vault_entity_id": vault_entity_id,
    }


def execute_investigation(
    *,
    agent_name,
    store_id,
    incident_id,
    vault_addr,
    role_id,
    secret_id,
    allowed_store_ids,
    investigation,
    db_path="data/storeguard_security_audit.sqlite3",
):
    """Authorize and execute one investigation with an audit trail.

    `investigation` is a callable executed only after authorization.
    `allowed_store_ids` must come from trusted backend configuration,
    never from the agent or an LLM.
    """
    run_id = str(uuid.uuid4())
    entity_id = None

    try:
        identity = authenticate_approle(
            vault_addr=vault_addr,
            role_id=role_id,
            secret_id=secret_id,
        )
        entity_id = identity.entity_id

        verify_agent_identity(agent_name, identity)

        if not authorize_investigation(
            agent_name=agent_name,
            store_id=store_id,
            incident_id=incident_id,
            allowed_store_ids=allowed_store_ids,
        ):
            raise ExecutionDenied("Investigation not authorized")

        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "AUTHORIZED", "Identity and scope verified", entity_id,
        ))

    except Exception as exc:
        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "DENIED", type(exc).__name__, entity_id,
        ))
        raise ExecutionDenied("StoreGuard execution denied") from exc

    try:
        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "STARTED", "Investigation started", entity_id,
        ))

        result = investigation()

        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "COMPLETED", "Investigation completed", entity_id,
        ))
        return {"run_id": run_id, "result": result}

    except Exception as exc:
        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "FAILED", type(exc).__name__, entity_id,
        ))
        raise
