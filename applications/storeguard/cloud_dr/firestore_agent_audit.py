"""Create-only Firestore evidence for StoreGuard agent decisions.

No agent tokens, SecretIDs, RoleIDs, or other credentials are stored.
Uses the isolated executive evidence database, never operational data.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

EVIDENCE_DATABASE = "storeguard-executive-evidence"
COLLECTION = "storeguard_agent_decisions"
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")

FIELDS = (
    "run_id",
    "agent_id",
    "incident_id",
    "store_id",
    "action",
    "delegation_id",
    "verified_subject",
    "evidence_id",
    "decision",
    "reason",
)


class FirestoreDecisionAudit:
    def __init__(self, *, client=None, project=None, database=None):
        selected = (
            database if database is not None
            else os.environ.get("STOREGUARD_EVIDENCE_DATABASE")
        )

        if selected != EVIDENCE_DATABASE:
            raise ValueError(
                "Refusing non-StoreGuard evidence database"
            )

        if client is None:
            from google.cloud import firestore

            selected_project = project or os.environ.get(
                "GOOGLE_CLOUD_PROJECT"
            )
            if not selected_project:
                raise ValueError("Google Cloud project required")

            client = firestore.Client(
                project=selected_project,
                database=selected,
            )
        else:
            # Injected clients are supported for offline unit tests.
            # Real clients must target the approved evidence database.
            actual = getattr(client, "_database", None)
            if actual is not None and actual != selected:
                raise ValueError("Firestore client database mismatch")

        self.client = client

    def append(self, record: dict) -> None:
        run_id = record.get("run_id")

        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("Invalid agent run ID")

        if record.get("decision") not in ("allow", "deny"):
            raise ValueError("Invalid authorization decision")

        # Only explicitly approved evidence fields may be persisted.
        # Never serialize arbitrary request bodies or credentials.
        data = {field: record.get(field) for field in FIELDS}
        data["recorded_at"] = datetime.now(timezone.utc).isoformat()

        # Firestore create() fails if this document already exists.
        # Never turn a failed audit write into authorization success.
        self.client.collection(COLLECTION).document(run_id).create(data)
