"""StoreGuard v0.9.1 compact mission cockpit.

Vault governs read-only investigation; human approval and DR are simulated.
"""
import os
import sqlite3
from pathlib import Path
import streamlit as st
from applications.storeguard.investigation_controller import AGENT_NAME
from applications.storeguard.scenario_orchestrator import Phase
from ui.storeguard.mission_operations import (
    ensure_mission_session, start_governed_tornado, advance_governed_tornado,
    collect_ai_investigation, demo_operator_approve, demo_post_checks,
    reset_view, ALLOWED_STORE_IDS, AUDIT_DB, TOKEN_FILE,
)

ensure_mission_session()
st.markdown("### 🛡️ StoreGuard · Mission Control")
scenario = st.session_state.get("tornado_scenario")
incident = st.session_state.get("incident")
store_id = str(scenario.store_id) if scenario else str(st.session_state.selected_store)
mode = (st.session_state.controller.stores[store_id].state.name
        if store_id in st.session_state.controller.stores else "UNKNOWN")
phase = scenario.phase if scenario else Phase.IDLE

# Mission controls remain above the auto-refreshing fragment.
with st.container():
    a, b, c, d = st.columns([1, 1, 1.35, 1.3])
    a.metric("Store", store_id)
    b.metric("Store state", mode)
    c.metric("Mission phase", phase.name)
    d.metric("Incident", str(incident.incident_id) if incident else "Not started")

    path = st.selectbox(
        "Scenario", ["successful_recovery", "rto_breach"],
        format_func=lambda x: "Successful restoration" if x == "successful_recovery"
        else "RTO breach / escalation", key="mission_path")
    if store_id not in ALLOWED_STORE_IDS:
        st.error(f"Store {store_id} is outside the configured Vault investigation scope.")
    if not TOKEN_FILE.is_file():
        st.warning("Restricted Vault provisioner token missing. Governed AI execution may fail.")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("▶ Start tornado demo", type="primary", use_container_width=True, key="mission_start"):
            start_governed_tornado(path)
            st.rerun()
    with b2:
        terminal = scenario is None or phase in (Phase.AWAITING_APPROVAL, Phase.ESCALATED, Phase.NORMAL)
        if st.button("⏸ Pause" if st.session_state.get("tornado_running", False) else "▶ Resume",
                     disabled=terminal, use_container_width=True, key="mission_pause"):
            st.session_state.tornado_running = not st.session_state.get("tornado_running", False)
            st.rerun()
    with b3:
        if st.button("↺ Reset", use_container_width=True, key="mission_reset"):
            reset_view()
            st.rerun()

    if phase == Phase.AWAITING_APPROVAL:
        st.warning("Human approval required · Simulated, not IBM Verify-authenticated")
        if st.button("👤 Simulate approval → RECOVERY", key="mission_approve", type="primary"):
            demo_operator_approve()
            st.rerun()
    elif phase == Phase.RECOVERY:
        if st.button("✓ Run simulated recovery checks → NORMAL", key="mission_verify", type="primary"):
            demo_post_checks()
            st.rerun()
    elif phase == Phase.ESCALATED:
        st.error("RTO breach · Escalated; automatic recovery not authorized")
    elif phase == Phase.NORMAL:
        st.success("Simulated recovery verified · Controller NORMAL")


def _incident_audit():
    if incident is None or not Path(AUDIT_DB).is_file():
        return []
    try:
        with sqlite3.connect(f"file:{Path(AUDIT_DB).resolve()}?mode=ro",uri=True,timeout=2) as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT timestamp,run_id,agent,store_id,incident_id,event_type,reason,vault_entity_id,vault_login_request_id "
                "FROM execution_events WHERE incident_id=? AND store_id=? AND agent=? "
                "ORDER BY timestamp ASC,rowid ASC LIMIT 300",
                (str(incident.incident_id),store_id,AGENT_NAME))]
    except (sqlite3.Error,OSError):
        return []


@st.fragment(run_every="1s")
def live_mission():
    # Advance in the UI thread; background AI worker never touches Streamlit state.
    changed=False
    if st.session_state.get("tornado_running",False):
        changed=advance_governed_tornado() or changed
    changed=collect_ai_investigation() or changed
    if changed:
        st.rerun(scope="app")
    active=st.session_state.get("tornado_scenario")
    phase=active.phase if active else Phase.IDLE
    incident_now=st.session_state.get("incident")
    events=st.session_state.get("events",[])
    audit=_incident_audit() if incident_now else []
    audit_names=[e["event_type"] for e in audit]
    ai_future=st.session_state.get("sg_ai_future")
    ai_pending=ai_future is not None and not ai_future.done()
    latest=st.session_state.get("sg_ai_latest")
    completed=bool(latest and latest[1].get("governed_run_id") and "COMPLETED" in audit_names)
    approved=any(e.event_type=="DEMO_APPROVAL" for e in events)
    verified=any(e.event_type=="DEMO_POST_CHECKS_PASSED" for e in events)
    check_done=any(e.event_type.startswith("SCENARIO_") and e.event_type!="SCENARIO_ERROR" for e in events)
    stages=[
      ("1 · Store check","Complete" if check_done else "Waiting"),
      ("2 · Vault + AI","Complete" if completed else "Running" if ai_pending else "Failed" if st.session_state.get("sg_ai_error") else "Waiting"),
      ("3 · Human review","Approved (simulated)" if approved else "Action required" if phase==Phase.AWAITING_APPROVAL else "Waiting"),
      ("4 · DR transition","Complete (simulated)" if approved and phase in (Phase.RECOVERY,Phase.NORMAL) else "Waiting"),
      ("5 · Verification","Complete (simulated)" if verified else "Waiting"),
    ]
    from ui.storeguard.hybrid_command_view import render_compact_cockpit
    render_compact_cockpit(
        store_id=store_id,
        phase=phase,
        incident=incident_now,
        controller=st.session_state.controller,
        agent_name=AGENT_NAME,
        stages=stages,
        events=events,
        audit=audit,
        latest=latest,
        ai_error=st.session_state.get("sg_ai_error"),
    )

live_mission()
