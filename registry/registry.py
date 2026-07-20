from dataclasses import dataclass

@dataclass
class AgentRecord:
    name: str
    owner: str
    environment: str
    purpose: str
    risk_level: str
    approved: bool
    status: str

AGENT_REGISTRY = {
    "sre-troubleshooting-agent": AgentRecord(
        name="sre-troubleshooting-agent",
        owner="platform-team",
        environment="dev",
        purpose="incident-response",
        risk_level="medium",
        approved=True,
        status="active",
    )
}

def get_agent_record(agent_name: str) -> AgentRecord | None:
    return AGENT_REGISTRY.get(agent_name)