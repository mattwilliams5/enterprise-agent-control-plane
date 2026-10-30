"""StoreGuard demo dashboard with real local state-machine transitions.

Weather and connectivity inputs are deterministic presentation fixtures.
Vault, Verify, and infrastructure authorization are NOT integrated.

Run from repository root:
    python3 -m streamlit run ui/storeguard/dashboard.py
"""


from applications.storeguard.ai_recovery_agent import run_recovery_agent
from applications.storeguard.recovery_agent import SystemHealth
from applications.storeguard.scenario_integration import SCENARIO_HEALTH
from applications.storeguard.ai_investigation import snapshot_for_phase, executive_question
from applications.storeguard.weather_intelligence import from_demo_incident, weather_view
from applications.storeguard.governed_recovery import (
    DemoApproval, issue_demo_approval, execute_demo_approval, execute_post_recovery_checks,
)




from dataclasses import replace
from html import escape
import time
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from applications.storeguard.controller import StoreGuardController
from applications.storeguard.scenario_integration import build_local_scenario
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError
from applications.storeguard.state_machine import StoreState
from ui.storeguard.demo_data import (
    build_demo_stores,
    demo_identity,
    tornado_fixture,
)
from ui.storeguard.incident_timeline import render_incident_timeline
from ui.storeguard.view_models import AgentEventView, Health, StoreMode


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="StoreGuard",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {
    padding-top: 1.4rem;
    max-width: 1500px;
}
.sg-eyebrow {
    font-size: .78rem;
    letter-spacing: .16em;
    text-transform: uppercase;
    opacity: .65;
}
.sg-title {
    font-size: 2.1rem;
    font-weight: 750;
    margin: .1rem 0 0 0;
}
.sg-subtitle {
    opacity: .7;
    margin-bottom: 1.2rem;
}
.sg-card {
    border: 1px solid rgba(128,128,128,.24);
    border-radius: 14px;
    padding: 16px;
    min-height: 118px;
}
.sg-small {
    font-size: .82rem;
    opacity: .72;
}
.sg-event {
    border-left: 3px solid rgba(128,128,128,.45);
    padding: 4px 0 4px 12px;
    margin: 8px 0;
}
.sg-ok {
    font-weight: 700;
}
.sg-warn {
    font-weight: 700;
}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

if "stores" not in st.session_state:
    st.session_state.stores = build_demo_stores()

if "incident" not in st.session_state:
    st.session_state.incident = None

if "events" not in st.session_state:
    st.session_state.events = []

if "selected_store" not in st.session_state:
    st.session_state.selected_store = "1847"


# ---------------------------------------------------------
# CONTROLLER INTEGRATION
# ---------------------------------------------------------

def build_controller(stores):
    """Create a controller and register all demo stores."""

    controller = StoreGuardController()

    for store in stores:
        controller.register_store(store.store_id)

    return controller


def request_store_transition(store_id, target, *, offline=False):
    """Update the view only after the controller accepts a transition."""

    store_id = str(store_id)
    controller = st.session_state.controller

    # The backend controller decides whether the transition is legal.
    allowed = controller.request_transition(store_id, target)

    if allowed:
        authoritative_state = controller.stores[store_id].state

        # Synchronize the GUI with the authoritative backend state.
        st.session_state.stores = [
            replace(
                store,
                mode=StoreMode[authoritative_state.name],
                health=Health.OFFLINE if offline else store.health,
            )
            if str(store.store_id) == store_id
            else store
            for store in st.session_state.stores
        ]

    # Record approved and denied transitions distinctly.
    st.session_state.events.append(
        AgentEventView(
            "STORE_TRANSITION_APPROVED"
            if allowed
            else "STORE_TRANSITION_DENIED",
            (
                f"Store {store_id}: requested {target.value}; "
                + (
                    "accepted by local state machine"
                    if allowed
                    else "rejected by local state machine"
                )
            ),
            "complete" if allowed else "denied",
        )
    )

    return allowed


def reset_view():
    """Reset the demonstration to its initial state."""

    st.session_state.stores = build_demo_stores()

    st.session_state.controller = build_controller(
        st.session_state.stores
    )

    st.session_state.incident = None
    st.session_state.events = []
    st.session_state.pop("tornado_scenario", None)
    st.session_state.pop("tornado_running", None)
    st.session_state.pop("tornado_last_tick", None)
    st.session_state.pop("sg_exec_ai_result", None)
    st.session_state.pop("sg_exec_ai_signature", None)
    st.session_state.pop("sg_exec_ai_error", None)
    st.session_state.pop("sg_ai_future", None)
    st.session_state.pop("sg_ai_pending_snapshot", None)
    st.session_state.pop("sg_ai_latest", None)
    st.session_state.pop("sg_ai_error", None)
    st.session_state.pop("sg_ai_queued_snapshot", None)
    st.session_state.pop("sg_ai_history", None)
    st.session_state.pop("sg_demo_approval", None)


def activate_fixture():
    """Load a deterministic tornado scenario."""

    # Reset first so repeated demonstrations are predictable.
    reset_view()

    fixture_stores, incident, events = tornado_fixture(
        st.session_state.stores
    )

    st.session_state.incident = incident
    st.session_state.events = list(events)

    # The fixture determines affected stores.
    # The controller determines whether state changes are allowed.
    for store_id in incident.affected_store_ids:
        request_store_transition(
            store_id,
            StoreState.PROTECTED,
        )

    # Retain weather-risk indicators from the fixture.
    # Do not treat fixture-supplied store modes as authoritative.
    fixture_by_id = {
        str(store.store_id): store
        for store in fixture_stores
    }

    st.session_state.stores = [
        replace(
            store,
            weather_risk=fixture_by_id[str(store.store_id)].weather_risk,
        )
        if str(store.store_id) in fixture_by_id
        else store
        for store in st.session_state.stores
    ]


def advance_maintenance_fixture():
    """Simulate connectivity loss and request maintenance mode."""

    store_id = str(st.session_state.selected_store)

    selected_store = next(
        (
            store
            for store in st.session_state.stores
            if str(store.store_id) == store_id
        ),
        None,
    )

    if selected_store is None:
        st.session_state.events.append(
            AgentEventView(
                "STORE_TRANSITION_DENIED",
                f"Store {store_id}: store not found",
                "denied",
            )
        )
        return

    # Record connectivity loss only once per offline episode.
    if selected_store.health != Health.OFFLINE:
        st.session_state.events.append(
            AgentEventView(
                "STORE_CONNECTIVITY_LOST",
                f"Simulated connectivity loss for store {store_id}",
            )
        )

    # Repeated requests are intentionally sent to the controller.
    # This demonstrates rejection of invalid state transitions.
    request_store_transition(
        store_id,
        StoreState.MAINTENANCE,
        offline=True,
    )


# ---------------------------------------------------------
# GOVERNED TORNADO WALKTHROUGH (DEMO-ONLY)
# ---------------------------------------------------------

def start_governed_tornado(path):
    """Initialize a fresh scenario without pre-transitioning the controller."""
    reset_view()
    fixture_stores, incident, fixture_events = tornado_fixture(st.session_state.stores)
    affected = {str(sid) for sid in incident.affected_store_ids}
    store_id = str(st.session_state.selected_store)
    if store_id not in affected:
        store_id = str(next(iter(incident.affected_store_ids)))
        st.session_state.selected_store = store_id
    st.session_state.incident = incident
    st.session_state.events = list(fixture_events)
    risk_by_id = {str(store.store_id): store.weather_risk for store in fixture_stores}
    st.session_state.stores = [
        replace(store, weather_risk=risk_by_id.get(str(store.store_id), store.weather_risk))
        for store in st.session_state.stores
    ]
    st.session_state.tornado_scenario = build_local_scenario(
        st.session_state.controller, store_id, path=path
    )
    st.session_state.tornado_running = True
    st.session_state.tornado_last_tick = time.monotonic()


@st.cache_resource
def investigation_pool():
    # One shared worker pool; no Streamlit API is used from worker threads.
    return ThreadPoolExecutor(max_workers=3, thread_name_prefix="storeguard-advisory")


def _investigate_snapshot(snapshot):
    """Background task. Never access st.session_state or mutate controller state."""
    return run_recovery_agent(
        store_id=snapshot.store_id,
        health=snapshot.health,
        elapsed_minutes=snapshot.elapsed_minutes,
        rto_minutes=30,
        question=executive_question(snapshot),
    )


def request_ai_investigation(snapshot, *, automatic=False):
    """Start one incident-bound read-only request without pausing orchestration."""
    future = st.session_state.get("sg_ai_future")
    if future is not None and not future.done():
        if automatic:
            st.session_state.sg_ai_queued_snapshot = snapshot
        return False  # Queue latest automatic evidence instead of flooding the API.
    st.session_state.sg_ai_future = investigation_pool().submit(_investigate_snapshot, snapshot)
    st.session_state.sg_ai_pending_snapshot = snapshot
    st.session_state.sg_ai_error = None
    st.session_state.events.append(AgentEventView(
        "AI_INVESTIGATION_STARTED",
        f"{'Automatic' if automatic else 'Operator-requested'} read-only AI investigation "
        f"for store {snapshot.store_id}, {snapshot.evidence_key} (simulated)",
        "working",
    ))
    return True


def collect_ai_investigation():
    """Only the Streamlit thread collects and displays worker results."""
    future = st.session_state.get("sg_ai_future")
    snapshot = st.session_state.get("sg_ai_pending_snapshot")
    if future is None or snapshot is None or not future.done():
        return False
    st.session_state.sg_ai_future = None
    st.session_state.sg_ai_pending_snapshot = None
    current = st.session_state.get("tornado_scenario")
    incident = st.session_state.get("incident")
    if current is None or incident is None or str(incident.incident_id) != snapshot.incident_id or current.store_id != snapshot.store_id:
        return True  # Discard any result from a reset/replaced incident.
    try:
        result = future.result()
        if st.session_state.get("sg_ai_latest") is not None:
            st.session_state.setdefault("sg_ai_history", []).append(st.session_state.sg_ai_latest)
        st.session_state.sg_ai_latest = (snapshot, result)
        st.session_state.sg_ai_error = None
        st.session_state.events.append(AgentEventView(
            "AI_INVESTIGATION_COMPLETE",
            f"Read-only AI advisory ready for store {snapshot.store_id} "
            f"using {snapshot.evidence_key} evidence", "complete"))
    except Exception as exc:
        st.session_state.sg_ai_error = str(exc)
        st.session_state.events.append(AgentEventView(
            "AI_INVESTIGATION_FAILED", f"AI advisory unavailable: {exc}", "error"))
    queued = st.session_state.pop("sg_ai_queued_snapshot", None)
    if queued is not None and current is not None and incident is not None:
        if queued.incident_id == str(incident.incident_id) and queued.store_id == current.store_id:
            request_ai_investigation(queued, automatic=True)
    return True


def _sync_focus_store():
    scenario = st.session_state.get("tornado_scenario")
    if scenario is None:
        return
    state = st.session_state.controller.stores[scenario.store_id].state
    st.session_state.stores = [
        replace(store, mode=StoreMode[state.name],
                health=Health.OFFLINE if state == StoreState.MAINTENANCE else store.health)
        if str(store.store_id) == scenario.store_id else store
        for store in st.session_state.stores
    ]


def demo_operator_approve():
    scenario = st.session_state.tornado_scenario
    incident = st.session_state.incident
    try:
        grant = issue_demo_approval(scenario, str(incident.incident_id), scenario.store_id,
                                    scenario.evidence_revision, operator_label="Demo operator")
        execute_demo_approval(scenario, grant, str(incident.incident_id))
        st.session_state.sg_demo_approval = grant
        _sync_focus_store()
        st.session_state.events.append(AgentEventView(
            "DEMO_APPROVAL", "SIMULATED operator approval (no IBM Verify authentication); controller entered RECOVERY", "complete"))
    except (ScenarioError, ValueError) as exc:
        st.session_state.events.append(AgentEventView("DEMO_APPROVAL_DENIED", str(exc), "denied"))


def demo_post_checks():
    scenario = st.session_state.tornado_scenario
    incident = st.session_state.incident
    try:
        execute_post_recovery_checks(scenario, st.session_state.sg_demo_approval,
                                     str(incident.incident_id), SCENARIO_HEALTH["services_restored"])
        _sync_focus_store()
        st.session_state.events.append(AgentEventView(
            "DEMO_POST_CHECKS_PASSED", "Simulated fresh health checks passed; controller entered NORMAL", "complete"))
    except (ScenarioError, ValueError) as exc:
        st.session_state.events.append(AgentEventView("DEMO_POST_CHECKS_DENIED", str(exc), "denied"))


def advance_governed_tornado():
    """Advance one deterministic step, then mirror controller state into the view."""
    scenario = st.session_state.get("tornado_scenario")
    if scenario is None or not st.session_state.get("tornado_running", False):
        return False
    now = time.monotonic()
    if now - st.session_state.get("tornado_last_tick", now) < 2.5:
        return False
    st.session_state.tornado_last_tick = now
    try:
        event = scenario.tick()
    except (ScenarioError, ValueError, KeyError) as exc:
        st.session_state.tornado_running = False
        st.session_state.events.append(AgentEventView("SCENARIO_ERROR", str(exc), "error"))
        return True
    if event is None:
        st.session_state.tornado_running = False
        return True

    store_id = scenario.store_id
    state = st.session_state.controller.stores[store_id].state
    st.session_state.stores = [
        replace(
            store,
            mode=StoreMode[state.name],
            health=(Health.OFFLINE if state == StoreState.MAINTENANCE else store.health),
        ) if str(store.store_id) == store_id else store
        for store in st.session_state.stores
    ]
    st.session_state.events.append(AgentEventView(
        "SCENARIO_" + event.phase.name, event.description, "complete"
    ))
    # Hard-down transition triggers one proactive, nonblocking AI investigation.
    if scenario.phase == Phase.MAINTENANCE:
        incident = st.session_state.incident
        snapshot = snapshot_for_phase(
            incident_id=incident.incident_id, store_id=store_id,
            evidence_revision=scenario.evidence_revision, phase=scenario.phase,
            controller_state=state.name,
        )
        request_ai_investigation(snapshot, automatic=True)
    if scenario.phase == Phase.FINAL_CHECK:
        incident = st.session_state.incident
        snapshot = snapshot_for_phase(
            incident_id=incident.incident_id, store_id=store_id,
            evidence_revision=scenario.evidence_revision, phase=scenario.phase,
            controller_state=state.name,
        )
        request_ai_investigation(snapshot, automatic=True)
    if scenario.phase in (Phase.AWAITING_APPROVAL, Phase.ESCALATED, Phase.NORMAL):
        st.session_state.tornado_running = False
    return True


if "controller" not in st.session_state:
    st.session_state.controller = build_controller(
        st.session_state.stores
    )


# ---------------------------------------------------------
# DASHBOARD HEADER
# ---------------------------------------------------------

st.markdown(
    '<div class="sg-eyebrow">Enterprise Agent Control Plane</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sg-title">🛡️ StoreGuard</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sg-subtitle">'
    'Agentic resilience for distributed enterprise operations'
    '</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# EXECUTIVE PRESENTATION MODE
# ---------------------------------------------------------

st.markdown("""<style>
.sg-exec-banner {border-radius:16px; padding:22px 26px; margin:10px 0 14px;
 border:2px solid var(--sg-accent); background:var(--sg-bg); color:var(--sg-fg);}
.sg-exec-kicker {font-size:.78rem;font-weight:750;letter-spacing:.13em;text-transform:uppercase;}
.sg-exec-head {font-size:1.8rem;font-weight:800;margin:5px 0;line-height:1.16;}
.sg-exec-desc {font-size:1rem;line-height:1.35;}
.sg-step {padding:11px 5px;border-radius:10px;text-align:center;font-weight:700;font-size:.86rem;
 border:1px solid rgba(128,128,128,.3);}
.sg-step-active {outline:3px solid #2563eb;outline-offset:2px;}
</style>""", unsafe_allow_html=True)

presentation_mode = st.radio(
    "Presentation mode", ["Executive view", "Technical view"],
    horizontal=True, key="sg_presentation_mode",
)

if presentation_mode == "Executive view":
    scenario = st.session_state.get("tornado_scenario")
    phase = scenario.phase if scenario is not None else Phase.IDLE
    phase_name = phase.value.replace("_", " ").title()
    if phase == Phase.IDLE:
        accent, bg, fg, heading, description = (
            "#15803d", "#dcfce7", "#14532d", "All systems normal",
            "Ready to demonstrate governed incident response.",
        )
    elif phase in (Phase.WEATHER_ALERT, Phase.PROTECTED):
        accent, bg, fg, heading, description = (
            "#ca8a04", "#fef9c3", "#713f12", "Severe weather detected",
            "StoreGuard is taking precautionary action for stores at risk.",
        )
    elif phase in (Phase.MAINTENANCE, Phase.DIAGNOSTICS, Phase.PARTIAL_RESTORATION, Phase.ESCALATED):
        accent, bg, fg, heading, description = (
            "#dc2626", "#fee2e2", "#7f1d1d",
            "Recovery time objective breached" if phase == Phase.ESCALATED else "Store operations disrupted",
            "Human escalation required. No recovery authorized." if phase == Phase.ESCALATED
            else "Critical services are unavailable. StoreGuard is checking recovery readiness.",
        )
    elif phase in (Phase.FINAL_CHECK, Phase.AWAITING_APPROVAL, Phase.RECOVERY):
        accent, bg, fg, heading, description = (
            "#2563eb", "#dbeafe", "#1e3a8a",
            "Human decision required" if phase == Phase.AWAITING_APPROVAL else "Recovery verification in progress",
            "Automated diagnostics are ready. The store remains in MAINTENANCE until an authorized human approves recovery."
            if phase == Phase.AWAITING_APPROVAL else "Final checks and governance requirements remain in effect.",
        )
    else:
        accent, bg, fg, heading, description = (
            "#15803d", "#dcfce7", "#14532d", "Recovery verified",
            "Post-recovery checks passed and normal operations restored.",
        )

    monitored = len(st.session_state.stores)
    affected = len(st.session_state.incident.affected_store_ids) if st.session_state.incident else 0
    store_id = scenario.store_id if scenario is not None else str(st.session_state.selected_store)
    controller_store = st.session_state.controller.stores.get(store_id)
    actual_state = controller_store.state.name if controller_store is not None else "UNKNOWN"
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Stores monitored", monitored)
    k2.metric("Stores at risk", affected)
    k3.metric("Focus store", f"#{store_id}")
    k4.metric("Actual store mode", actual_state)

    # Weather is a separate input signal, not proof that a store is offline.
    weather_event = from_demo_incident(st.session_state.incident)
    weather_info = weather_view(weather_event, compact=phase in (
        Phase.FINAL_CHECK, Phase.AWAITING_APPROVAL, Phase.RECOVERY, Phase.NORMAL,
    ))
    if weather_event is not None:
        if weather_info["compact"]:
            with st.expander("🌪️ Incident origin · Weather intelligence (simulated)", expanded=False):
                st.markdown(f"**{weather_info['headline']}**")
                st.caption(weather_info["detail"])
                st.caption(f"Incident {weather_event.incident_id} · {weather_info['badge']} · No live weather API")
        else:
            with st.container(border=True):
                st.caption("🌪️ WEATHER INTELLIGENCE  ·  SIMULATED FORECAST / SCENARIO")
                st.markdown(f"**{weather_info['headline']}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Threat", weather_event.event_type)
                c2.metric("Severity", weather_event.severity)
                c3.metric("Stores exposed", len(weather_event.affected_store_ids))
                st.caption("Affected: " + ", ".join(f"#{s}" for s in weather_event.affected_store_ids))
                st.caption("Scenario fixture only · No live forecast, alert feed, or meteorological measurements")
    else:
        st.caption("🌤️ Weather intelligence ready · No active simulated event · Live provider not connected")

    st.markdown(
        f'<div class="sg-exec-banner" style="--sg-accent:{accent};--sg-bg:{bg};--sg-fg:{fg}">'
        f'<div class="sg-exec-kicker">{phase_name} · Simulated incident</div>'
        f'<div class="sg-exec-head">{heading}</div>'
        f'<div class="sg-exec-desc">{description}</div></div>',
        unsafe_allow_html=True,
    )

    stages = [
        ("Weather alert", (Phase.WEATHER_ALERT,)),
        ("Protect", (Phase.PROTECTED,)),
        ("Store down", (Phase.MAINTENANCE, Phase.DIAGNOSTICS, Phase.PARTIAL_RESTORATION)),
        ("Final checks", (Phase.FINAL_CHECK,)),
        ("Human gate", (Phase.AWAITING_APPROVAL, Phase.RECOVERY)),
    ]
    stage_colors = ["#eab308", "#eab308", "#dc2626", "#2563eb", "#2563eb"]
    active_index = next((i for i, (_, phases) in enumerate(stages) if phase in phases), -1)
    if phase in (Phase.ESCALATED, Phase.NORMAL):
        active_index = 2 if phase == Phase.ESCALATED else len(stages)
    stage_columns = st.columns(5)
    for i, (label, _) in enumerate(stages):
        color = stage_colors[i]
        complete = i < active_index
        active = i == active_index
        style = (
            f"background:{color};color:white;border-color:{color};"
            if active else
            ("background:#e5e7eb;color:#374151;border-color:#d1d5db;" if complete
             else "background:transparent;color:inherit;")
        )
        marker = "●" if active else ("✓" if complete else "○")
        stage_columns[i].markdown(
            f'<div class="sg-step" style="{style}">{marker} {label}</div>',
            unsafe_allow_html=True,
        )

    st.progress(min(1.0, len(scenario.events) / 8) if scenario is not None else 0.0)
    st.caption("Yellow: warning  ·  Red: disruption  ·  Blue: human decision  ·  Green: verified normal")

    controls, current = st.columns([1.05, 1.1])
    with controls:
        st.markdown("**Presentation controls**")
        chosen_path = st.selectbox(
            "Scenario path", ["successful_recovery", "rto_breach"],
            format_func=lambda v: "Successful restoration" if v == "successful_recovery" else "RTO breach / escalation",
            key="sg_exec_path",
        )
        st.button("▶ Start tornado walkthrough", on_click=start_governed_tornado,
                  args=(chosen_path,), width="stretch", key="sg_exec_start")

        @st.fragment(run_every="2s")
        def executive_playback():
            active = st.session_state.get("tornado_scenario")
            c_pause, c_reset = st.columns(2)
            terminal = active is None or active.phase in (
                Phase.AWAITING_APPROVAL, Phase.ESCALATED, Phase.NORMAL)
            with c_pause:
                if st.button(
                    "⏸ Pause" if st.session_state.get("tornado_running", False) else "▶ Resume",
                    disabled=terminal, width="stretch", key="sg_exec_pause",
                ):
                    st.session_state.tornado_running = not st.session_state.get("tornado_running", False)
                    st.rerun(scope="app")
            with c_reset:
                if st.button("↺ Reset", width="stretch", key="sg_exec_reset"):
                    reset_view()
                    st.rerun(scope="app")
            if active is not None and st.session_state.get("tornado_running", False):
                if advance_governed_tornado():
                    st.rerun(scope="app")

        executive_playback()
    with current:
        st.markdown("**What StoreGuard is doing**")
        if scenario is None:
            st.info("Press Start to run the tornado demonstration.")
        elif phase == Phase.AWAITING_APPROVAL:
            st.info("🔒 **Human approval checkpoint.** Automatic recovery is blocked. This demonstration can simulate an operator approval; IBM Verify is not connected.")
            st.button("👤 Simulate operator approval → RECOVERY",
                      key="sg_exec_demo_approve", on_click=demo_operator_approve, width="stretch")
        elif phase == Phase.RECOVERY:
            st.info("🔍 **RECOVERY.** Simulated operator approval recorded. Fresh deterministic post-recovery checks are required before NORMAL.")
            st.button("✓ Run post-recovery checks → NORMAL",
                      key="sg_exec_post_checks", on_click=demo_post_checks, width="stretch")
        elif phase == Phase.NORMAL:
            st.success("✅ **Verified NORMAL (simulation).** Local controller confirms NORMAL after simulated approval and fresh post-recovery checks.")
        elif phase == Phase.ESCALATED:
            st.error("⛔ **RTO breach.** Escalation required; store remains in MAINTENANCE.")
        else:
            latest = scenario.events[-1].description if scenario.events else "Preparing scenario"
            st.write(latest)
            st.caption("Running automatically" if st.session_state.get("tornado_running", False)
                       else "Paused / completed")
        st.caption("Deterministic demo. IBM Verify, Vault and production approval are not connected.")

    # AI analysis is proactively triggered at hard-down, but never controls the scenario.
    if scenario is not None and phase in (
        Phase.MAINTENANCE, Phase.DIAGNOSTICS, Phase.PARTIAL_RESTORATION,
        Phase.FINAL_CHECK, Phase.AWAITING_APPROVAL, Phase.ESCALATED,
    ):
        st.markdown("### 🤖 AI Recovery Analyst")
        incident_id = st.session_state.incident.incident_id
        controller_state = st.session_state.controller.stores[scenario.store_id].state.name
        current_snapshot = snapshot_for_phase(
            incident_id=incident_id, store_id=scenario.store_id,
            evidence_revision=scenario.evidence_revision, phase=phase,
            controller_state=controller_state,
        )
        st.caption(
            f"Store #{scenario.store_id} · {current_snapshot.evidence_key.replace('_', ' ').title()} "
            f"· Simulated incident time: {current_snapshot.elapsed_minutes} minutes "
            f"· Controller: {controller_state}"
        )
        pending = st.session_state.get("sg_ai_future")
        if st.button(
            f"🔍 {'Refresh analysis' if st.session_state.get('sg_ai_latest') else 'Analyze Store'} #{scenario.store_id}",
            key="sg_exec_analyze", type="primary", width="stretch",
            disabled=pending is not None and not pending.done(),
        ):
            request_ai_investigation(current_snapshot, automatic=False)
            st.rerun()

        @st.fragment(run_every="1s")
        def executive_ai_status():
            # Polling happens in the Streamlit thread; the worker never touches UI/state.
            if collect_ai_investigation():
                st.rerun(scope="app")
            pending_future = st.session_state.get("sg_ai_future")
            if pending_future is not None:
                st.info("🔎 AI investigating simulated store outage in the background. Incident response continues.")
            latest = st.session_state.get("sg_ai_latest")
            if latest is not None:
                captured, result = latest
                current = st.session_state.get("tornado_scenario")
                if current is not None:
                    current_mode = st.session_state.controller.stores[current.store_id].state.name
                    fresh = snapshot_for_phase(
                        incident_id=st.session_state.incident.incident_id,
                        store_id=current.store_id,
                        evidence_revision=current.evidence_revision,
                        phase=current.phase,
                        controller_state=current_mode,
                    ) if current.phase in (
                        Phase.MAINTENANCE, Phase.DIAGNOSTICS, Phase.PARTIAL_RESTORATION,
                        Phase.FINAL_CHECK, Phase.AWAITING_APPROVAL, Phase.ESCALATED,
                    ) else None
                    stale = fresh is None or captured.signature != fresh.signature
                else:
                    stale = True
                if stale:
                    st.warning(
                        f"Historical AI advisory — based on {captured.evidence_key.replace('_', ' ')} "
                        f"at simulated minute {captured.elapsed_minutes}. "
                        "Evidence has changed; refresh before making a decision."
                    )
                else:
                    st.info("Read-only AI advisory for the displayed evidence. No approval or state change authorized.")
                # Current controller mode always comes from authoritative state, never LLM prose.
                if current is not None:
                    st.write(f"**Authoritative store mode: {current_mode}.** "
                             "Healthy diagnostics do not authorize normal operations.")
                st.markdown(result.get("analysis", "No analysis returned."))
                with st.expander("How the AI reached this recommendation · tool evidence"):
                    for activity in result.get("tool_activity", []):
                        st.write(f"Tool: `{activity.get('tool', 'unknown')}`")
                        st.json(activity.get("evidence", {}))
            history = st.session_state.get("sg_ai_history", [])
            if history:
                with st.expander(f"Previous AI assessments ({len(history)})"):
                    for old_snapshot, old_result in reversed(history):
                        st.caption(f"Historical: {old_snapshot.evidence_key} · minute {old_snapshot.elapsed_minutes}")
                        st.markdown(old_result.get("analysis", "No analysis returned."))
            if st.session_state.get("sg_ai_error"):
                st.error("AI investigation unavailable: " + st.session_state.sg_ai_error)
            st.caption("Simulated evidence · No live Verify/Vault authorization · AI cannot transition store state")

        executive_ai_status()

    with st.expander("Recent activity (last 5 events)"):
        for event in st.session_state.events[-5:]:
            st.write(f"{event.event_type}: {event.message}")
    st.caption("For full fleet details, audit history, diagnostics, and AI analysis, switch to Technical view.")

else:

    # ---------------------------------------------------------
    # FLEET METRICS
    # ---------------------------------------------------------

    stores = st.session_state.stores

    normal = sum(
        store.mode == StoreMode.NORMAL
        for store in stores
    )

    protected = sum(
        store.mode == StoreMode.PROTECTED
        for store in stores
    )

    maintenance = sum(
        store.mode == StoreMode.MAINTENANCE
        for store in stores
    )

    recovery = sum(
        store.mode == StoreMode.RECOVERY
        for store in stores
    )

    m1, m2, m3, m4, m5 = st.columns(5)

    m1.metric("Stores monitored", len(stores))
    m2.metric("Normal", normal)
    m3.metric("Protected", protected)
    m4.metric("Maintenance", maintenance)
    m5.metric("Recovery", recovery)


    # ---------------------------------------------------------
    # MAIN DASHBOARD PANELS
    # ---------------------------------------------------------

    left, center, right = st.columns([1.1, 1.5, 1.0])


    # WEATHER INTELLIGENCE AND CONTROLS

    with left:
        st.subheader("Weather intelligence")

        if st.session_state.incident:
            incident = st.session_state.incident

            st.warning(f"🌪️ {incident.title}")

            st.caption(
                f"Incident {incident.incident_id} "
                f"· Severity {incident.severity}"
            )

            st.write(
                "**Affected stores:** "
                + ", ".join(
                    f"#{store_id}"
                    for store_id in incident.affected_store_ids
                )
            )

        else:
            st.success("No active severe-weather incident")
            st.caption("Weather provider integration pending")

        st.subheader("Demo controls")

        st.caption(
            "Simulated weather/connectivity; state changes validated "
            "by the local Python controller. "
            "No Vault/Verify enforcement yet."
        )

        st.subheader("Automated tornado walkthrough")
        st.caption("Deterministic simulation only. No live Vault/Verify authorization or recovery approval.")
        scenario_path = st.selectbox(
            "Scenario path",
            ["successful_recovery", "rto_breach"],
            format_func=lambda value: "Successful restoration" if value == "successful_recovery" else "RTO breach / escalation",
            key="tornado_path",
        )
        st.button(
            "▶ Start tornado walkthrough",
            width="stretch",
            on_click=start_governed_tornado,
            args=(scenario_path,),
        )

        @st.fragment(run_every="1s")
        def tornado_playback():
            active = st.session_state.get("tornado_scenario")
            if active is None:
                st.caption("Walkthrough not started")
                return
            st.write(f"**Store #{active.store_id} · {active.phase.value.replace('_', ' ').title()}**")
            if active.phase == Phase.AWAITING_APPROVAL:
                st.warning("Human approval required. Simulated operator approval available in Executive View.")
            elif active.phase == Phase.ESCALATED:
                st.error("RTO breached. Escalated for human intervention.")
            c_pause, c_reset = st.columns(2)
            with c_pause:
                if st.button(
                    "⏸ Pause" if st.session_state.get("tornado_running", False) else "▶ Resume",
                    disabled=active.phase in (Phase.AWAITING_APPROVAL, Phase.ESCALATED, Phase.NORMAL),
                    key="tornado_pause_resume",
                ):
                    st.session_state.tornado_running = not st.session_state.get("tornado_running", False)
                    st.rerun(scope="app")
            with c_reset:
                if st.button("↺ Reset walkthrough", key="tornado_reset"):
                    reset_view()
                    st.rerun(scope="app")
            if st.session_state.get("tornado_running", False):
                if advance_governed_tornado():
                    st.rerun(scope="app")

        tornado_playback()
        st.divider()
        st.caption("Manual presentation controls (reset the automated walkthrough)")
        st.button(
            "🌪️ Load tornado presentation fixture",
            width="stretch",
            on_click=activate_fixture,
        )

        st.button(
            "📴 Show selected store offline",
            width="stretch",
            on_click=advance_maintenance_fixture,
            disabled=st.session_state.incident is None,
        )

        st.button(
            "↺ Reset presentation",
            width="stretch",
            on_click=reset_view,
        )


    # AGENT ACTIVITY

    with center:
        st.subheader("Agent activity")

        if not st.session_state.events:
            st.info(
                "No active agent session. "
                "Local demonstration events will appear here."
            )

        for event in st.session_state.events:
            if event.status == "denied":
                glyph = "⛔"
            elif event.status == "working":
                glyph = "◉"
            elif event.status == "pending":
                glyph = "◷"
            elif event.status == "error":
                glyph = "!"
            else:
                glyph = "✓"

            st.markdown(
                f'<div class="sg-event">'
                f'<b>{glyph} {escape(str(event.message))}</b><br>'
                f'<span class="sg-small">'
                f'{escape(str(event.timestamp))} · '
                f'{escape(str(event.event_type))}'
                f'</span></div>',
                unsafe_allow_html=True,
            )


    # IDENTITY AND AUTHORIZATION

    with right:
        st.subheader("Identity & authorization")

        identity = demo_identity()

        st.markdown(
            f"**Human identity**  \n"
            f"{identity.provider}: {identity.human_status}"
        )

        st.markdown(
            f"**Agent**  \n`{identity.agent_name}`"
        )

        st.markdown(
            f"**Vault**  \n{identity.vault_status}"
        )

        st.markdown(
            f"**Credential**  \n{identity.credential_status}"
        )

        st.caption(
            "This panel will show real Verify/Vault state "
            "when those integrations are connected."
        )


    # ---------------------------------------------------------
    # STORE FLEET
    # ---------------------------------------------------------

    st.divider()
    st.subheader("Store fleet")

    store_ids = [
        store.store_id
        for store in stores
    ]

    st.session_state.selected_store = st.selectbox(
        "Inspect store",
        store_ids,
        index=(
            store_ids.index(st.session_state.selected_store)
            if st.session_state.selected_store in store_ids
            else 0
        ),
    )

    selected = next(
        store
        for store in stores
        if store.store_id == st.session_state.selected_store
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Store", f"#{selected.store_id}")
    c2.metric("Location", f"{selected.city}, {selected.state}")
    c3.metric("Environment", selected.cloud)
    c4.metric("Weather risk", selected.weather_risk)


    # ---------------------------------------------------------
    # STORE STATUS / MAINTENANCE PANELS
    # ---------------------------------------------------------

    if selected.mode == StoreMode.MAINTENANCE:

        st.error(
            f"Store #{selected.store_id} "
            "· MAINTENANCE MODE · OFFLINE"
        )

        f1, f2, f3, f4 = st.columns(4)

        with f1:
            st.markdown(
                '<div class="sg-card">'
                '<b>Finances of the day</b><br><br>'
                '<span class="sg-small">'
                'Awaiting finance service integration'
                '</span></div>',
                unsafe_allow_html=True,
            )

        with f2:
            st.markdown(
                '<div class="sg-card">'
                '<b>Inventory last call</b><br><br>'
                '<span class="sg-small">'
                'Awaiting inventory service integration'
                '</span></div>',
                unsafe_allow_html=True,
            )

        with f3:
            st.markdown(
                '<div class="sg-card">'
                '<b>Safety protocols</b><br><br>'
                '<span class="sg-small">'
                'Awaiting safety workflow integration'
                '</span></div>',
                unsafe_allow_html=True,
            )

        with f4:
            st.markdown(
                '<div class="sg-card">'
                '<b>Online</b><br><br>'
                '<b>WAITING FOR RECOVERY</b>'
                '</div>',
                unsafe_allow_html=True,
            )

    else:
        st.success(
            f"Store #{selected.store_id} "
            f"· {selected.mode.value} "
            f"· {selected.health.value}"
        )


    # ---------------------------------------------------------
    # INCIDENT TIMELINE
    # ---------------------------------------------------------

    st.divider()

    render_incident_timeline(
        st.session_state.events
    )


    # ---------------------------------------------------------
    # AUDIT TRAIL
    # ---------------------------------------------------------

    st.divider()
    st.subheader("Audit trail")

    if st.session_state.events:

        rows = [
            {
                "Time": event.timestamp,
                "Event": event.event_type,
                "Status": event.status,
                "Message": event.message,
            }
            for event in st.session_state.events
        ]

        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )

    else:
        st.caption(
            "Local demonstration events. "
            "External audit persistence and tamper-evident storage "
            "are not yet integrated."
        )


    # ---------------------------------------------------------
    # AI RECOVERY ANALYST
    # ---------------------------------------------------------

    st.divider()
    st.subheader("🤖 AI Recovery Analyst")

    st.caption(
        "LLM-assisted analysis using simulated health evidence. "
        "Read-only: no recovery actions or approvals."
    )

    if "ai_analysis" not in st.session_state:
        st.session_state.ai_analysis = None

    if "ai_analysis_store" not in st.session_state:
        st.session_state.ai_analysis_store = None


    # ---------------------------------------------------------
    # DYNAMIC HEALTH SCENARIOS
    # ---------------------------------------------------------

    SCENARIOS = {
        "Initial outage": {
            "connectivity": False,
            "inventory": False,
            "payments": True,
            "safety": True,
            "orders": True,
        },
        "Partial restoration": {
            "connectivity": True,
            "inventory": False,
            "payments": True,
            "safety": True,
            "orders": True,
        },
        "Services restored": {
            "connectivity": True,
            "inventory": True,
            "payments": True,
            "safety": True,
            "orders": True,
        },
    }

    scenario = st.selectbox(
        "Simulated diagnostic scenario",
        list(SCENARIOS),
        key=f"health_scenario_{selected.store_id}",
    )

    health = SystemHealth(**SCENARIOS[scenario])

    st.caption(
        "Health values are simulated diagnostic evidence. "
        "They do not represent live monitoring."
    )

    h1, h2, h3, h4, h5 = st.columns(5)

    for column, (name, healthy) in zip(
        [h1, h2, h3, h4, h5],
        health.model_dump().items(),
    ):
        column.metric(
            name.capitalize(),
            "Healthy" if healthy else "Unhealthy",
        )


    question = st.text_area(
        "Ask the Recovery Analyst",
        value=(
            f"Analyze Store {selected.store_id}, identify operational "
            "risks, and recommend the next action."
        ),
        key=f"ai_question_{selected.store_id}",
    )

    elapsed_minutes = st.slider(
        "Minutes elapsed since incident",
        min_value=0,
        max_value=35,
        value=10,
        step=5,
    )

    evidence_signature = (
        str(selected.store_id),
        scenario,
        elapsed_minutes,
    )

    if st.session_state.get("ai_evidence_signature") != evidence_signature:
        st.session_state.ai_analysis = None
    if st.button("🔍 Analyze selected store", type="primary"):
        with st.spinner("Analyzing StoreGuard recovery evidence..."):
            try:
                result = run_recovery_agent(
                    store_id=str(selected.store_id),
                    health=health,
                    elapsed_minutes=elapsed_minutes,
                    rto_minutes=30,
                    question=question,
                )

                st.session_state.ai_analysis = result
                st.session_state.ai_evidence_signature = evidence_signature
                st.session_state.ai_analysis_store = str(
                    selected.store_id
                )

            except Exception as exc:
                st.session_state.ai_analysis = None
                st.error(f"AI analysis failed: {exc}")

    if (
        st.session_state.ai_analysis is not None
        and st.session_state.ai_analysis_store
        == str(selected.store_id)
    ):
        result = st.session_state.ai_analysis

        st.markdown("### AI recommendation")
        st.markdown(result["analysis"])

        with st.expander("Agent tool activity"):
            for activity in result["tool_activity"]:
                st.write(f"Tool: `{activity['tool']}`")
                st.json(activity["evidence"])
