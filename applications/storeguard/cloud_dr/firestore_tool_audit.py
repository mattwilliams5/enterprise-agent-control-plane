"""Create-only Firestore audit for protected StoreGuard tool events.

The trusted runner supplies event metadata. Never persist credentials,
request bodies, or arbitrary agent-provided fields.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from uuid import uuid4

DATABASE = "storeguard-executive-evidence"
COLLECTION = "storeguard_agent_tool_events"
EVENT_TYPES = frozenset({
    "DENIED",
    "STARTED",
    "COMPLETED",
    "FAILED",
    "DENIED_OR_UNCONFIRMED",
})
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class FirestoreToolAudit:
    def __init__(self, *, client=None, project=None, database=None):
        selected = (
            database if database is not None
            else os.environ.get("STOREGUARD_EVIDENCE_DATABASE")
        )
        if selected != DATABASE:
            raise ValueError("Refusing non-evidence Firestore database")

        if client is None:
            from google.cloud import firestore

            selected_project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not selected_project:
                raise ValueError("Google Cloud project required")

            client = firestore.Client(
                project=selected_project,
                database=selected,
            )
        else:
            actual = getattr(client, "_database", None)
            if actual is not None and actual != selected:
                raise ValueError("Firestore client database mismatch")

        self.client = client

    def append(self, *, action_run_id, event_type, intent, reason):
        if not isinstance(action_run_id, str) or not ID_PATTERN.fullmatch(
            action_run_id
        ):
            raise ValueError("Invalid action run ID")

        if event_type not in EVENT_TYPES:
            raise ValueError("Unknown tool event type")

        fields = (
            "agent_id",
            "incident_id",
            "store_id",
            "action",
            "delegation_id",
        )
        values = {}
        for field in fields:
            value = getattr(intent, field, None)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid tool intent")
            if len(value) > 256:
                raise ValueError("Tool intent field too long")
            values[field] = value

        if not isinstance(reason, str) or not reason or len(reason) > 256:
            raise ValueError("Invalid audit reason")

        event_id = uuid4().hex
        record = {
            "event_id": event_id,
            "action_run_id": action_run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "reason": reason,
            **values,
        }

        # Each event receives a unique document. No update/upsert is used.
        self.client.collection(COLLECTION).document(event_id).create(record)
        return event_id
