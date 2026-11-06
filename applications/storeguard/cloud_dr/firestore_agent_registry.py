"""Read-only, fail-closed Firestore agent registration adapter.

All authorization lookups are fresh. Registry writes and revocations
must be performed by a separately authorized administrative workflow.
"""
from __future__ import annotations

import os
import re

EVIDENCE_DATABASE = "storeguard-executive-evidence"
COLLECTION = "storeguard_agent_registry"
AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


class FirestoreAgentRegistry:
    def __init__(self, *, client=None, project=None, database=None):
        selected = (
            database if database is not None
            else os.environ.get("STOREGUARD_EVIDENCE_DATABASE")
        )
        if selected != EVIDENCE_DATABASE:
            raise ValueError("Invalid agent registry database")

        if client is None:
            from google.cloud import firestore

            selected_project = project or os.environ.get(
                "GOOGLE_CLOUD_PROJECT"
            )
            if not selected_project:
                raise ValueError("Google Cloud project required")
            client = firestore.Client(
                project=selected_project, database=selected
            )
        else:
            actual = getattr(client, "_database", None)
            if actual is not None and actual != selected:
                raise ValueError("Registry client database mismatch")

        self.client = client

    def get_record(self, agent_id: str):
        if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
            return None

        # Explicit server read for each check; no local authorization cache.
        snapshot = (
            self.client.collection(COLLECTION)
            .document(agent_id)
            .get()
        )
        if not snapshot.exists:
            return None

        record = snapshot.to_dict()
        if not isinstance(record, dict):
            return None
        if record.get("agent_id") != agent_id:
            return None
        return record

    def is_active(self, agent_id: str) -> bool:
        record = self.get_record(agent_id)
        return bool(
            record
            and record.get("approved") is True
            and record.get("status") == "active"
            and record.get("revoked") is False
            and isinstance(record.get("vault_entity_id"), str)
            and bool(record["vault_entity_id"].strip())
        )

    def matches_identity(
        self, agent_id: str, vault_entity_id: str
    ) -> bool:
        if not isinstance(vault_entity_id, str) or not vault_entity_id:
            return False

        # Independently reload the record for the identity-bound check.
        record = self.get_record(agent_id)
        return bool(
            record
            and record.get("approved") is True
            and record.get("status") == "active"
            and record.get("revoked") is False
            and record.get("vault_entity_id") == vault_entity_id
        )
