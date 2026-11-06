"""Local live-Vault integration smoke test; not a production agent runner."""

import sqlite3

from identity.execution_gate import ExecutionDenied, execute_investigation
from scripts.show_id_demo import fresh_credentials, VAULT_ADDR, DB

AGENT = "sre-troubleshooting-agent"
INCIDENT = "INC-LIVE-001"


def execute(store_id):
    role_id, secret_id = fresh_credentials()

    calls = []

    def investigation():
        calls.append("executed")
        return {"health": "checked", "store_id": store_id}

    try:
        result = execute_investigation(
            agent_name=AGENT,
            store_id=store_id,
            incident_id=INCIDENT,
            vault_addr=VAULT_ADDR,
            role_id=role_id,
            secret_id=secret_id,
            allowed_store_ids=frozenset({"1847"}),
            investigation=investigation,
            db_path=DB,
        )
        print(f"{store_id}: ALLOWED, run={result['run_id']}")
        assert calls == ["executed"]
        return result["run_id"]

    except ExecutionDenied:
        print(f"{store_id}: DENIED, callback_executed={bool(calls)}")
        assert calls == []
        return None


allowed_run = execute("1847")
denied_run = execute("9999")

assert allowed_run is not None
assert denied_run is None

with sqlite3.connect(DB) as db:
    events = db.execute(
        """
        SELECT event_type, store_id, reason
        FROM execution_events
        ORDER BY timestamp
        """
    ).fetchall()

for event in events:
    print(event)

assert [e[0] for e in events if e[1] == "1847"][-4:] == [
    "AUTHORIZED", "STARTED", "COMPLETED", "TOKEN_REVOKED"
]
assert [e[0] for e in events if e[1] == "9999"][-1:] == ["DENIED"]

print("PASS: Live Vault execution gate and audit lifecycle")
