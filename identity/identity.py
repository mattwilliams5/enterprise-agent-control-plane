from dataclasses import dataclass

@dataclass
class AgentIdentity:
    name: str
    owner: str
    envirnoment: str
    purpose: str

def get_agent_identity() -> AgentIdentity:
    return AgentIdentity(
        name="sre-troubleshooting-agent",
        owner="platform-team",
        environment="dev",
        purpose="incident-response",
    )