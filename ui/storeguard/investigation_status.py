"""Run-specific investigation status for StoreGuard Mission Control.

Presentation-only correlation. This module does not authorize agent actions,
modify incident state, or change Vault security controls.
"""


def investigation_stage_status(*, latest, audit, ai_pending=False, ai_error=None):
    """Return the current Vault + AI mission-stage status."""
    if ai_pending:
        return "Running"

    if ai_error:
        return "Failed"

    if not latest:
        return "Waiting"

    snapshot, result = latest
    if not isinstance(result, dict):
        return "Waiting"

    run_id = result.get("governed_run_id")
    if not run_id:
        return "Waiting"

    incident_id = getattr(snapshot, "incident_id", None)
    store_id = getattr(snapshot, "store_id", None)

    completed = any(
        str(event.get("run_id")) == str(run_id)
        and event.get("event_type") == "COMPLETED"
        and incident_id is not None
        and str(event.get("incident_id")) == str(incident_id)
        and store_id is not None
        and str(event.get("store_id")) == str(store_id)
        for event in audit
    )

    return "Complete" if completed else "Waiting"
