from unittest.mock import Mock, patch

import pytest

from applications.storeguard.investigation_controller import (
    InvestigationController,
    InvestigationRequest,
)
from identity.execution_gate import ExecutionDenied


def make_request(store_id="1847", incident_id="INC-1847"):
    return InvestigationRequest(
        store_id=store_id,
        incident_id=incident_id,
        health=object(),
        elapsed_minutes=10,
        rto_minutes=30,
        question="Assess store health",
    )


def make_controller(runner, provider):
    return InvestigationController(
        vault_addr="http://127.0.0.1:8200",
        credential_provider=provider,
        allowed_store_ids=frozenset({"1847"}),
        investigation_runner=runner,
    )


def test_controller_passes_request_to_gate():
    runner = Mock()
    provider = Mock(return_value=("role", "secret"))
    controller = make_controller(runner, provider)

    with patch(
        "applications.storeguard.investigation_controller.execute_investigation",
        return_value={"run_id": "test-run", "result": {}},
    ) as gate:
        result = controller.investigate(make_request())

    assert result["run_id"] == "test-run"
    provider.assert_called_once()
    gate.assert_called_once()
    assert gate.call_args.kwargs["allowed_store_ids"] == frozenset({"1847"})


def test_out_of_scope_request_never_provisions_credentials():
    runner = Mock()
    provider = Mock()
    controller = make_controller(runner, provider)

    with pytest.raises(ExecutionDenied):
        controller.investigate(make_request(store_id="9999"))

    provider.assert_not_called()
    runner.assert_not_called()


def test_missing_incident_is_rejected():
    runner = Mock()
    provider = Mock()
    controller = make_controller(runner, provider)

    with pytest.raises(ValueError):
        controller.investigate(make_request(incident_id=""))

    provider.assert_not_called()
    runner.assert_not_called()


def test_out_of_scope_denial_is_audited(tmp_path):
    import sqlite3

    runner = Mock()
    provider = Mock()

    controller = InvestigationController(
        vault_addr="http://127.0.0.1:8200",
        credential_provider=provider,
        allowed_store_ids=frozenset({"1847"}),
        investigation_runner=runner,
        db_path=str(tmp_path / "audit.sqlite3"),
    )

    with pytest.raises(ExecutionDenied):
        controller.investigate(make_request(store_id="9999"))

    provider.assert_not_called()
    runner.assert_not_called()

    with sqlite3.connect(tmp_path / "audit.sqlite3") as db:
        events = db.execute(
            "SELECT event_type, store_id FROM execution_events"
        ).fetchall()

    assert events == [("DENIED", "9999")]
