from datetime import datetime, UTC


def log_action(agent_name: str, action: str, allowed: bool) -> dict:
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent": agent_name,
        "action": action,
        "allowed": allowed,
    }

    return event

def log_security_decision(
    *,
    run_id: str,
    agent_name: str,
    store_id: str,
    incident_id: str,
    action: str,
    allowed: bool,
    reason: str,
    vault_entity_id: str | None = None,
) -> dict:
    """Build an audit event for one agent execution decision.

    Never include Vault tokens, SecretIDs, or other credentials.
    """
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "agent": agent_name,
        "store_id": store_id,
        "incident_id": incident_id,
        "action": action,
        "allowed": allowed,
        "reason": reason,
        "vault_entity_id": vault_entity_id,
    }
