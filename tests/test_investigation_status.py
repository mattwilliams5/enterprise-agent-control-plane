"""Regression tests for StoreGuard investigation evidence correlation."""

from types import SimpleNamespace

from ui.storeguard.investigation_status import investigation_stage_status


def latest(run_id="run-current"):
    snapshot = SimpleNamespace(
        incident_id="WX-2026-001",
        store_id="1847",
    )
    return snapshot, {"governed_run_id": run_id}


def audit_event(
    run_id="run-current",
    event_type="COMPLETED",
    incident_id="WX-2026-001",
    store_id="1847",
):
    return {
        "run_id": run_id,
        "event_type": event_type,
        "incident_id": incident_id,
        "store_id": store_id,
    }


def test_matching_completed_run():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event()],
    ) == "Complete"


def test_previous_completed_run_does_not_count():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event(run_id="run-previous")],
    ) == "Waiting"


def test_current_failure_overrides_previous_success():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event()],
        ai_error="Vault authentication failed",
    ) == "Failed"


def test_pending_investigation_is_running():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event()],
        ai_pending=True,
    ) == "Running"


def test_wrong_incident_does_not_count():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event(incident_id="WX-OTHER")],
    ) == "Waiting"


def test_wrong_store_does_not_count():
    assert investigation_stage_status(
        latest=latest(),
        audit=[audit_event(store_id="9999")],
    ) == "Waiting"


def test_missing_governed_run_is_not_success():
    assert investigation_stage_status(
        latest=latest(run_id=None),
        audit=[audit_event()],
    ) == "Waiting"


def test_no_latest_result_is_waiting():
    assert investigation_stage_status(
        latest=None,
        audit=[audit_event()],
    ) == "Waiting"
