"""
Policy Engine

This module controls what actions an AI agent
is authorized to perform.

Enterprise concept:
Identity tells us WHO the agent is.
Policy tells us WHAT the agent can do.
"""


POLICIES = {
    "sre-troubleshooting-agent": [
        "read_logs",
        "check_health",
    ]
}


def is_action_allowed(agent_name: str, action: str) -> bool:
    """
    Check whether an agent is allowed to perform
    a requested action.

    Args:
        agent_name: Unique identity of the AI agent
        action: Requested capability/action

    Returns:
        True if action is allowed
        False if action is denied
    """

    allowed_actions = POLICIES.get(agent_name, [])

    return action in allowed_actions

def authorize_investigation(
    *,
    agent_name: str,
    store_id: str,
    incident_id: str,
    allowed_store_ids: frozenset[str],
) -> bool:
    """Authorize one read-only investigation against explicit scope."""
    if not store_id or not incident_id:
        return False

    if store_id not in allowed_store_ids:
        return False

    return is_action_allowed(agent_name, "check_health")
