"""Development-only StoreGuard Show ID execution harness.

The CLI is a trusted local provisioner, NOT an agent runtime.
Never embed its provisioning credential in Streamlit or an agent.
"""
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from identity.vault_identity import authenticate_approle
from identity.show_id import verify_agent_identity
from policy.engine import authorize_investigation
from registry.registry import get_agent_record

AGENT = "sre-troubleshooting-agent"
ROLE = "storeguard-investigator"
VAULT_ADDR = "http://127.0.0.1:8200"
DB = Path("data/storeguard_security_audit.sqlite3")
ALLOWED_STORES = frozenset({"1847"})


def vault_cli(*args, token=None):
    env = os.environ.copy()
    env["VAULT_ADDR"] = VAULT_ADDR
    if token:
        env["VAULT_TOKEN"] = token

    result = subprocess.run(
        ["vault", *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def fresh_credentials():
    token_file = Path("/tmp/storeguard-provisioner-token.json")
    if not token_file.is_file():
        raise RuntimeError("Provisioner token file is missing")

    provisioner = json.loads(token_file.read_text())["auth"]["client_token"]

    # RoleID is a public identifier, but only the trusted CLI retrieves it.
    role_id = vault_cli(
        "read", "-field=role_id",
        f"auth/approle/role/{ROLE}/role-id",
        token=provisioner,
    )

    secret_response = vault_cli(
        "write", "-format=json", "-f",
        f"auth/approle/role/{ROLE}/secret-id",
        token=provisioner,
    )
    secret_id = json.loads(secret_response)["data"]["secret_id"]
    return role_id, secret_id


def init_audit():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                store_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                vault_entity_id TEXT,
                registration_status TEXT NOT NULL
            )
        """)


def execute(store_id, incident_id):
    run_id = str(uuid.uuid4())
    entity_id = None
    decision = "DENY"
    reason = "Authentication or authorization did not complete"
    registration_status = "UNVERIFIED"

    try:
        role_id, secret_id = fresh_credentials()
        identity = authenticate_approle(
            vault_addr=VAULT_ADDR,
            role_id=role_id,
            secret_id=secret_id,
        )
        entity_id = identity.entity_id

        verify_agent_identity(AGENT, identity)
        registration_status = "MATCHED"

        record = get_agent_record(AGENT)
        if record is None:
            raise PermissionError("Registration missing")

        permitted = authorize_investigation(
            agent_name=AGENT,
            store_id=store_id,
            incident_id=incident_id,
            allowed_store_ids=ALLOWED_STORES,
        )

        if permitted:
            decision = "ALLOW"
            reason = "Identity matched; investigation within trusted store scope"
        else:
            reason = "Investigation outside authorized scope or policy"

    except Exception as exc:
        # Do not persist or display credentials or raw Vault errors.
        reason = f"Execution denied: {type(exc).__name__}"

    event = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": AGENT,
        "store_id": store_id,
        "incident_id": incident_id,
        "action": "check_health",
        "decision": decision,
        "reason": reason,
        "vault_entity_id": entity_id,
        "registration_status": registration_status,
    }

    # Audit persistence must succeed before reporting an allow.
    with sqlite3.connect(DB) as conn:
        conn.execute(
            """INSERT INTO security_events VALUES
               (:run_id, :timestamp, :agent, :store_id,
                :incident_id, :action, :decision, :reason,
                :vault_entity_id, :registration_status)""",
            event,
        )

    return event


if __name__ == "__main__":
    init_audit()

    for store in ("1847", "9999"):
        event = execute(store, f"DEMO-{store}")
        print(json.dumps(event, indent=2))

    print(f"\nAudit database: {DB}")
