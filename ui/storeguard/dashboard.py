
from applications.storeguard.ai_recovery_agent import run_recovery_agent
from applications.storeguard.recovery_agent import SystemHealth


"""StoreGuard demo dashboard with real local state-machine transitions.

Weather and connectivity inputs are deterministic presentation fixtures.
Vault, Verify, and infrastructure authorization are NOT integrated.

Run from repository root:
    python3 -m streamlit run ui/storeguard/dashboard.py
"""

from dataclasses import replace
from html import escape

import streamlit as st

from applications.storeguard.controller import StoreGuardController
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

if selected.mode == StoreMode.MAINTENANCE:
    st.warning(
        "Demo assumption: connectivity and inventory are unhealthy. "
        "Other required systems are healthy."
    )

    health = SystemHealth(
        connectivity=False,
        inventory=False,
        payments=True,
        safety=True,
        orders=True,
    )
else:
    st.info(
        "Demo assumption: all required systems are healthy. "
        "This is not a live service-health check."
    )

    health = SystemHealth(
        connectivity=True,
        inventory=True,
        payments=True,
        safety=True,
        orders=True,
    )

question = st.text_area(
    "Ask the Recovery Analyst",
    value=(
        f"Analyze Store {selected.store_id}, identify operational "
        "risks, and recommend the next action."
    ),
    key=f"ai_question_{selected.store_id}",
)

if st.button("🔍 Analyze selected store", type="primary"):
    with st.spinner("Analyzing StoreGuard recovery evidence..."):
        try:
            result = run_recovery_agent(
                store_id=str(selected.store_id),
                health=health,
                elapsed_minutes=10,
                rto_minutes=30,
                question=question,
            )

            st.session_state.ai_analysis = result
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
