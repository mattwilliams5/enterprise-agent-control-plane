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
from registry.fingerprint import registration_fingerprint
from identity.vault_identity import managed_approle_session, VaultRevocationError
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
        columns = {
            row[1] for row in db.execute(
                "PRAGMA table_info(execution_events)"
            )
        }
        if "vault_login_request_id" not in columns:
            db.execute(
                "ALTER TABLE execution_events "
                "ADD COLUMN vault_login_request_id TEXT"
            )
        if "registration_fingerprint" not in columns:
            db.execute(
                "ALTER TABLE execution_events "
                "ADD COLUMN registration_fingerprint TEXT"
            )

        db.execute("""
            INSERT INTO execution_events (
                event_id, run_id, timestamp, agent,
                store_id, incident_id, action, event_type,
                reason, vault_entity_id, registration_fingerprint,
                vault_login_request_id
            ) VALUES (
                :event_id, :run_id, :timestamp, :agent,
                :store_id, :incident_id, :action, :event_type,
                :reason, :vault_entity_id, :registration_fingerprint,
                :vault_login_request_id
            )
        """, event)


def _event(run_id, agent, store_id, incident_id, event_type,
           reason, vault_entity_id=None, vault_login_request_id=None):
    try:
        fingerprint = registration_fingerprint(agent)
    except ValueError:
        fingerprint = None

    return {
        "registration_fingerprint": fingerprint,
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
        "vault_login_request_id": vault_login_request_id,
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
    """Authorize, execute, audit, and clean up one investigation."""
    run_id = str(uuid.uuid4())
    entity_id = None
    login_request_id = None
    authorized = False
    execution_started = False
    investigation_failed = False
    cleanup_audit_error = None

    def record_token_revoked():
        nonlocal cleanup_audit_error
        try:
            _record(db_path, _event(
                run_id, agent_name, store_id, incident_id,
                "TOKEN_REVOKED",
                "Vault self-revocation acknowledged",
                entity_id,
            ))
        except Exception as exc:
            cleanup_audit_error = exc

    try:
        with managed_approle_session(
            vault_addr=vault_addr,
            role_id=role_id,
            secret_id=secret_id,
            on_token_revoked=record_token_revoked,
        ) as identity:
            entity_id = identity.entity_id
            login_request_id = identity.login_request_id

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
                login_request_id,
            ))
            authorized = True

            _record(db_path, _event(
                run_id, agent_name, store_id, incident_id,
                "STARTED", "Investigation started", entity_id,
            ))
            execution_started = True

            try:
                result = investigation()
            except Exception:
                investigation_failed = True
                _record(db_path, _event(
                    run_id, agent_name, store_id, incident_id,
                    "INVESTIGATION_FAILED",
                    "Investigation callback raised",
                    entity_id,
                ))
                raise

            _record(db_path, _event(
                run_id, agent_name, store_id, incident_id,
                "COMPLETED", "Investigation completed", entity_id,
            ))

        if cleanup_audit_error is not None:
            raise cleanup_audit_error

        return {"run_id": run_id, "result": result}

    except VaultRevocationError:
        _record(db_path, _event(
            run_id, agent_name, store_id, incident_id,
            "REVOCATION_FAILED", "Vault token revocation unconfirmed", entity_id,
        ))
        raise

    except Exception as exc:
        if investigation_failed:
            if cleanup_audit_error is not None:
                if exc is cleanup_audit_error:
                    raise
                raise ExceptionGroup(
                    "Investigation and cleanup audit both failed",
                    [exc, cleanup_audit_error],
                ) from exc
            raise

        if cleanup_audit_error is not None:
            raise

        event_type = "FAILED" if execution_started else "DENIED"

        try:
            _record(db_path, _event(
                run_id, agent_name, store_id, incident_id,
                event_type, type(exc).__name__, entity_id,
            ))
        except Exception:
            # Preserve the original failure. The caller must still fail closed.
            raise

        if not authorized:
            raise ExecutionDenied("StoreGuard execution denied") from exc

        raise
