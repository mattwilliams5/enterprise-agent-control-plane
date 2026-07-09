from agent.agent import run_agent


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