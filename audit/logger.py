from datetime import datetime, UTC


def log_action(agent_name: str, action: str, allowed: bool) -> dict:
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent": agent_name,
        "action": action,
        "allowed": allowed,
    }

    return event