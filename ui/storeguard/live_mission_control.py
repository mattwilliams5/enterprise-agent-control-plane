"""StoreGuard Live Mission Control: interactive governed demo.

Simulated tornado and DR state transitions. Vault governs the read-only AI
investigation; operator approval is simulated and not IBM Verify authenticated.
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
st.title("🛡️ StoreGuard | Live Mission Control")
st.caption("One-screen tornado response · Vault-governed AI investigation · Simulated human-approved recovery")
scenario=st.session_state.get("tornado_scenario")
incident=st.session_state.get("incident")
store_id=str(scenario.store_id) if scenario else str(st.session_state.selected_store)
mode=st.session_state.controller.stores[store_id].state.name if store_id in st.session_state.controller.stores else "UNKNOWN"

c1,c2,c3,c4=st.columns(4)
c1.metric("Focus store",store_id)
c2.metric("Controller mode",mode)
c3.metric("Registered agent",AGENT_NAME)
c4.metric("Incident",str(incident.incident_id) if incident else "Not started")

st.subheader("Run the live demonstration")
path=st.selectbox("Tornado scenario",["successful_recovery","rto_breach"],
    format_func=lambda x: "Successful restoration" if x=="successful_recovery" else "RTO breach / escalation",
    key="mission_path")
if store_id not in ALLOWED_STORE_IDS:
    st.error(f"Store {store_id} is outside the configured Vault investigation scope; AI execution will be denied.")
if not TOKEN_FILE.is_file():
    st.warning("Restricted Vault provisioner token is missing. The tornado can run, but the governed AI check will fail until the token is refreshed.")

b1,b2,b3=st.columns(3)
with b1:
    if st.button("▶ Start tornado & governed agent demo",type="primary",use_container_width=True,key="mission_start"):
        start_governed_tornado(path)
        st.rerun()
with b2:
    terminal=scenario is None or scenario.phase in (Phase.AWAITING_APPROVAL,Phase.ESCALATED,Phase.NORMAL)
    if st.button("⏸ Pause" if st.session_state.get("tornado_running",False) else "▶ Resume",
                 disabled=terminal,use_container_width=True,key="mission_pause"):
        st.session_state.tornado_running=not st.session_state.get("tornado_running",False)
        st.rerun()
with b3:
    if st.button("↺ Reset",use_container_width=True,key="mission_reset"):
        reset_view()
        st.rerun()

scenario=st.session_state.get("tornado_scenario")
phase=scenario.phase if scenario else Phase.IDLE
if phase==Phase.AWAITING_APPROVAL:
    st.warning("Human decision checkpoint: automatic recovery is blocked. IBM Verify is not connected; this approval is simulated.")
    if st.button("👤 Simulate operator approval → RECOVERY",key="mission_approve",type="primary"):
        demo_operator_approve()
        st.rerun()
elif phase==Phase.RECOVERY:
    st.info("Recovery state entered after simulated human approval. Verify before returning to NORMAL.")
    if st.button("✓ Run post-recovery checks → NORMAL",key="mission_verify",type="primary"):
        demo_post_checks()
        st.rerun()
elif phase==Phase.ESCALATED:
    st.error("RTO breach path: escalated; no automatic recovery authorized.")
elif phase==Phase.NORMAL:
    st.success("Simulated recovery verification completed; local controller is NORMAL.")


def _incident_audit():
    if incident is None or not Path(AUDIT_DB).is_file():
        return []
    try:
        with sqlite3.connect(f"file:{Path(AUDIT_DB).resolve()}?mode=ro",uri=True,timeout=2) as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT timestamp,run_id,agent,store_id,incident_id,event_type,reason,vault_entity_id "
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
    st.subheader("Continuous mission progression")
    cols=st.columns(5)
    for col,(name,status) in zip(cols,stages):
        with col:
            st.markdown(f"**{name}**")
            if status.startswith(("Complete","Approved")):
                st.success(status)
            elif status=="Failed":
                st.error(status)
            else:
                st.info(status)
    st.caption(f"Scenario phase: {phase.name} · AI authorization is enforced by Vault; DR state changes remain human-controlled simulations.")
    left,right=st.columns(2)
    with left:
        st.subheader("Operational activity")
        if events:
            st.dataframe([{"Time":str(e.timestamp),"Event":e.event_type,"Status":e.status,"Detail":e.message}
                          for e in reversed(events[-18:])],hide_index=True,use_container_width=True)
        else:
            st.info("Press Start to begin the incident.")
        if latest:
            with st.expander("AI recovery recommendation",expanded=True):
                st.markdown(latest[1].get("analysis","No analysis returned."))
                st.caption("Advisory only. The model cannot approve or execute DR.")
        if st.session_state.get("sg_ai_error"):
            st.error("Governed investigation failed. Check Vault provisioner token, policy and server logs. No authorization is implied.")
    with right:
        st.subheader("Live Vault security & audit")
        st.write(f"**Agent:** `{AGENT_NAME}`")
        if not audit:
            st.info("No Vault audit events for this incident yet. Events will appear as the governed agent executes.")
        else:
            runs={r["run_id"] for r in audit}
            st.caption(f"Incident-bound runs: {len(runs)} · Development SQLite audit")
            st.dataframe([{"UTC":r["timestamp"],"Run ID":r["run_id"],"Event":r["event_type"],
                           "Vault entity":r["vault_entity_id"],"Reason":r["reason"]}
                          for r in reversed(audit[-25:])],hide_index=True,use_container_width=True)
            if "REVOCATION_FAILED" in audit_names:
                st.error("Vault token revocation failure recorded")
            elif "TOKEN_REVOKED" in audit_names:
                st.success("Vault token revocation acknowledged in the audit")
            else:
                st.warning("No token revocation acknowledgement recorded yet")
        st.caption("Vault protects the AI investigation. DR is a deterministic simulation; operator approval is not authenticated by IBM Verify.")

live_mission()
