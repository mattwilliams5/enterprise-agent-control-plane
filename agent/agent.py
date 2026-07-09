from identity.identity import get_agent_identity
from policy.engine import is_action_allowed
from audit.logger import log_action

def run_agent(action: str) -> dict:
    identity = get_agent_identity()

    allowed = is_action_allowed(identity.name, action)

    audit_event = log_action(identity.name, action, allowed)

    if not allowed:
        audit_event["result"] = "denied"
        return audit_event

    audit_event["result"] = "completed"
    return audit_event

