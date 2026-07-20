from identity.identity import get_agent_identity
from policy.engine import is_action_allowed
from audit.logger import log_action
from registry.registry import get_agent_record

def run_agent(action: str) -> dict:
    identity = get_agent_identity()
    record = get_agent_record(identity.name)

    if record is None:
        audit_event = log_action(identity.name, action, False)
        audit_event["result"] = "unregistered"
        return audit_event

    if not record.approved or record.status != "active":
        audit_event = log_action(identity.name, action, False)
        audit_event["result"] = "agent_not_active"
        return audit_event

    allowed = is_action_allowed(identity.name, action)

    audit_event = log_action(identity.name, action, allowed)

    if not allowed:
        audit_event["result"] = "denied"
        return audit_event

    audit_event["result"] = "completed"
    return audit_event

