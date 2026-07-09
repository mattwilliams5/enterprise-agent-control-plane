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