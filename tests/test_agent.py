from agent.agent import run_agent
from registry.registry import AGENT_REGISTRY

def test_agent_can_read_logs():
    result = run_agent("read_logs")

    assert result["allowed"] is True
    assert result["result"] == "completed"
    assert result["action"] == "read_logs"


def test_agent_cannot_delete_database():
    result = run_agent("delete_database")

    assert result["allowed"] is False
    assert result["result"] == "denied"
    assert result["action"] == "delete_database"

def test_unapproved_agent_cannot_run():
    record = AGENT_REGISTRY["sre-troubleshooting-agent"]
    original_approved = record.approved

    try:
        record.approved = False

        result = run_agent("read_logs")

        assert result["allowed"] is False
        assert result["result"] == "agent_not_active"
    finally:
        record.approved = original_approved