"""Authoritative Firestore checks for StoreGuard demo agents.

Fresh server reads on each authorization. No cached grants.
"""
from datetime import datetime, timezone

DATABASE = "storeguard-executive-evidence"


def build_permission_checks(*, client):
    if getattr(client, "_database", None) != DATABASE:
        raise ValueError("Wrong Firestore database")

    def delegation_check(*, identity, intent, run_id):
        if not run_id or not intent.delegation_id:
            return False

        snap = (
            client.collection("storeguard_agent_delegations")
            .document(intent.delegation_id)
            .get()
        )
        if not snap.exists:
            return False

        record = snap.to_dict()
        if not isinstance(record, dict):
            return False

        expires = record.get("expires_at")
        if not isinstance(expires, datetime) or expires.tzinfo is None:
            return False

        return (
            record.get("approved") is True
            and record.get("revoked") is False
            and record.get("delegation_id") == intent.delegation_id
            and record.get("agent_id") == identity.agent_id
            and record.get("vault_entity_id") == identity.workload_subject
            and record.get("incident_id") == intent.incident_id
            and record.get("store_id") == intent.store_id
            and record.get("action") == intent.action
            and expires > datetime.now(timezone.utc)
        )

    def scope_check(*, identity, intent, run_id):
        if not run_id:
            return False

        snap = (
            client.collection("storeguard_agent_registry")
            .document(intent.agent_id)
            .get()
        )
        if not snap.exists:
            return False

        record = snap.to_dict()
        if not isinstance(record, dict):
            return False

        return (
            record.get("agent_id") == identity.agent_id
            and record.get("vault_entity_id") == identity.workload_subject
            and record.get("approved") is True
            and record.get("status") == "active"
            and record.get("revoked") is False
            and intent.incident_id in record.get("allowed_incident_ids", [])
            and intent.store_id in record.get("allowed_store_ids", [])
            and intent.action in record.get("allowed_actions", [])
        )

    return delegation_check, scope_check
