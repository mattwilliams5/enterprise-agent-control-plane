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
    vault_entity_id: str | None = None


AGENT_REGISTRY = {
    "sre-troubleshooting-agent": AgentRecord(
        name="sre-troubleshooting-agent",
        owner="platform-team",
        environment="dev",
        purpose="incident-response",
        risk_level="medium",
        approved=True,
        status="active",
        vault_entity_id="69a625b6-e6b7-3fb7-a82a-04dc19af4b24",
    )
}


def get_agent_record(agent_name: str) -> AgentRecord | None:
    return AGENT_REGISTRY.get(agent_name)
