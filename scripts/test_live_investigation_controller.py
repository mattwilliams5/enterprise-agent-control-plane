"""Development-only integration smoke test: controller -> Vault -> gate."""

import sqlite3
import tempfile
from pathlib import Path

from applications.storeguard.investigation_controller import (
    InvestigationController,
    InvestigationRequest,
)
from identity.execution_gate import ExecutionDenied
from scripts.show_id_demo import fresh_credentials, VAULT_ADDR


def request(store_id):
    return InvestigationRequest(
        store_id=store_id,
        incident_id=f"INC-LIVE-{store_id}",
        health={"status": "degraded"},
        elapsed_minutes=10,
        rto_minutes=30,
        question="Assess store health",
    )


with tempfile.TemporaryDirectory() as directory:
    db_path = Path(directory) / "audit.sqlite3"
    executed = []

    def runner(**kwargs):
        executed.append(kwargs["store_id"])
        return {"assessment": "completed"}

    controller = InvestigationController(
        vault_addr=VAULT_ADDR,
        credential_provider=fresh_credentials,
        allowed_store_ids=frozenset({"1847"}),
        investigation_runner=runner,
        db_path=str(db_path),
    )

    allowed = controller.investigate(request("1847"))
    assert allowed["result"] == {"assessment": "completed"}
    assert executed == ["1847"]
    print("1847: AUTHORIZED -> STARTED -> COMPLETED")

    try:
        controller.investigate(request("9999"))
        raise AssertionError("Out-of-scope request was not denied")
    except ExecutionDenied:
        assert executed == ["1847"]
        print("9999: DENIED before credential provisioning")

    with sqlite3.connect(db_path) as db:
        events = db.execute(
            "SELECT event_type, store_id FROM execution_events "
            "ORDER BY timestamp"
        ).fetchall()

    print("Persisted events:", events)

    assert events == [
        ("AUTHORIZED", "1847"),
        ("STARTED", "1847"),
        ("COMPLETED", "1847"),
        ("DENIED", "9999"),
    ]

    print("PASS: Controller -> Vault -> execution gate")
