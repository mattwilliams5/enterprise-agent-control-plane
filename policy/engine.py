POLICIES = {"sre-troubleshooting-agent": ["read_logs", "check_health"]}

def is_action_allowed(agent_name: str, action: str) -> bool:
    allowed_actions = POLICIES.get(agent_name, [])
    
    return action in allowed_actions