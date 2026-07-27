from agent.agent import run_agent
from registry.registry import AGENT_REGISTRY


def test_agent_can_read_logs():
    result = run_agent("read_logs")

    assert result["allowed"] is True
    assert result["result"] == "completed"
    assert result["action"] == "read_logs"

    assert "credential" in result
    assert result["credential"]["agent"] == "sre-troubleshooting-agent"
    assert result["credential"]["resource"] == "log-service"
    assert result["credential"]["ttl_seconds"] == 300
    assert "lease_id" in result["credential"]
    assert "token" in result["credential"]
    assert "issued_at" in result["credential"]
    assert "expires_at" in result["credential"]


def test_agent_cannot_delete_database():
    result = run_agent("delete_database")

    assert result["allowed"] is False
    assert result["result"] == "denied"
    assert result["action"] == "delete_database"
    assert "credential" not in result


def test_unapproved_agent_cannot_run():
    record = AGENT_REGISTRY["sre-troubleshooting-agent"]
    original_approved = record.approved

    try:
        record.approved = False

        result = run_agent("read_logs")

        assert result["allowed"] is False
        assert result["result"] == "agent_not_active"
        assert "credential" not in result
    finally:
        record.approved = original_approved