from datetime import datetime


def log_action(agent_name: str, action: str, allowed: bool) -> dict:
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent_name,
        "action": action,
        "allowed": allowed,
    }

    return event