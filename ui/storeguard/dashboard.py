from ui.storeguard.incident_timeline import render_incident_timeline
"""StoreGuard presentation layer.

Run from the repository root with:
    streamlit run ui/storeguard/dashboard.py

The demo controls below exercise presentation fixtures only. They do not make
policy decisions or simulate Vault/Terraform responses as if they were real.
"""
from dataclasses import replace
import streamlit as st

from ui.storeguard.demo_data import build_demo_stores, demo_identity, tornado_fixture
from ui.storeguard.view_models import Health, StoreMode

st.set_page_config(page_title="StoreGuard", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
.sg-eyebrow {font-size:.78rem; letter-spacing:.16em; text-transform:uppercase; opacity:.65;}
.sg-title {font-size:2.1rem; font-weight:750; margin:.1rem 0 0 0;}
.sg-subtitle {opacity:.7; margin-bottom:1.2rem;}
.sg-card {border:1px solid rgba(128,128,128,.24); border-radius:14px; padding:16px; min-height:118px;}
.sg-small {font-size:.82rem; opacity:.72;}
.sg-event {border-left:3px solid rgba(128,128,128,.45); padding:4px 0 4px 12px; margin:8px 0;}
.sg-ok {font-weight:700;}
.sg-warn {font-weight:700;}
</style>
""", unsafe_allow_html=True)

if "stores" not in st.session_state:
    st.session_state.stores = build_demo_stores()
if "incident" not in st.session_state:
    st.session_state.incident = None
if "events" not in st.session_state:
    st.session_state.events = []
if "selected_store" not in st.session_state:
    st.session_state.selected_store = "1847"


def reset_view():
    st.session_state.stores = build_demo_stores()
    st.session_state.incident = None
    st.session_state.events = []


def activate_fixture():
    stores, incident, events = tornado_fixture(st.session_state.stores)
    st.session_state.stores = stores
    st.session_state.incident = incident
    st.session_state.events = events


def advance_maintenance_fixture():
    # Presentation fixture only; the real transition rules will live in the
    # StoreGuard state machine we build together.
    st.session_state.stores = [
        replace(s, mode=StoreMode.MAINTENANCE, health=Health.OFFLINE)
        if s.store_id == st.session_state.selected_store else s
        for s in st.session_state.stores
    ]
    from ui.storeguard.view_models import AgentEventView
    st.session_state.events += [
        AgentEventView("STORE_CONNECTIVITY_LOST", f"Store {st.session_state.selected_store} is offline"),
        AgentEventView("MAINTENANCE_MODE_REQUESTED", "Maintenance presentation state requested", "working"),
    ]


st.markdown('<div class="sg-eyebrow">Enterprise Agent Control Plane</div>', unsafe_allow_html=True)
st.markdown('<div class="sg-title">🛡️ StoreGuard</div>', unsafe_allow_html=True)
st.markdown('<div class="sg-subtitle">Agentic resilience for distributed enterprise operations</div>', unsafe_allow_html=True)

stores = st.session_state.stores
normal = sum(s.mode == StoreMode.NORMAL for s in stores)
protected = sum(s.mode == StoreMode.PROTECTED for s in stores)
maintenance = sum(s.mode == StoreMode.MAINTENANCE for s in stores)
recovery = sum(s.mode == StoreMode.RECOVERY for s in stores)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Stores monitored", len(stores))
m2.metric("Normal", normal)
m3.metric("Protected", protected)
m4.metric("Maintenance", maintenance)
m5.metric("Recovery", recovery)

left, center, right = st.columns([1.1, 1.5, 1.0])

with left:
    st.subheader("Weather intelligence")
    if st.session_state.incident:
        i = st.session_state.incident
        st.warning(f"🌪️ {i.title}")
        st.caption(f"Incident {i.incident_id} · Severity {i.severity}")
        st.write("**Affected stores:** " + ", ".join(f"#{x}" for x in i.affected_store_ids))
    else:
        st.success("No active severe-weather incident")
        st.caption("Weather provider integration pending")

    st.subheader("Demo controls")
    st.caption("Visual fixtures only — not the production state machine.")
    st.button("🌪️ Load tornado presentation fixture", use_container_width=True, on_click=activate_fixture)
    st.button("📴 Show selected store offline", use_container_width=True, on_click=advance_maintenance_fixture,
              disabled=st.session_state.incident is None)
    st.button("↺ Reset presentation", use_container_width=True, on_click=reset_view)

with center:
    st.subheader("Agent activity")
    if not st.session_state.events:
        st.info("No active agent session. Events from the control plane will appear here.")
    for event in st.session_state.events:
        glyph = "◉" if event.status == "working" else "✓"
        st.markdown(
            f'<div class="sg-event"><b>{glyph} {event.message}</b><br>'
            f'<span class="sg-small">{event.timestamp} · {event.event_type}</span></div>',
            unsafe_allow_html=True,
        )

with right:
    st.subheader("Identity & authorization")
    identity = demo_identity()
    st.markdown(f"**Human identity**  \n{identity.provider}: {identity.human_status}")
    st.markdown(f"**Agent**  \n`{identity.agent_name}`")
    st.markdown(f"**Vault**  \n{identity.vault_status}")
    st.markdown(f"**Credential**  \n{identity.credential_status}")
    st.caption("This panel will show real Verify/Vault state when those integrations are connected.")

st.divider()
st.subheader("Store fleet")
store_ids = [s.store_id for s in stores]
st.session_state.selected_store = st.selectbox(
    "Inspect store",
    store_ids,
    index=store_ids.index(st.session_state.selected_store) if st.session_state.selected_store in store_ids else 0,
)
selected = next(s for s in stores if s.store_id == st.session_state.selected_store)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Store", f"#{selected.store_id}")
c2.metric("Location", f"{selected.city}, {selected.state}")
c3.metric("Environment", selected.cloud)
c4.metric("Weather risk", selected.weather_risk)

if selected.mode == StoreMode.MAINTENANCE:
    st.error(f"Store #{selected.store_id} · MAINTENANCE MODE · OFFLINE")
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.markdown('<div class="sg-card"><b>Finances of the day</b><br><br><span class="sg-small">Awaiting finance service integration</span></div>', unsafe_allow_html=True)
    with f2:
        st.markdown('<div class="sg-card"><b>Inventory last call</b><br><br><span class="sg-small">Awaiting inventory service integration</span></div>', unsafe_allow_html=True)
    with f3:
        st.markdown('<div class="sg-card"><b>Safety protocols</b><br><br><span class="sg-small">Awaiting safety workflow integration</span></div>', unsafe_allow_html=True)
    with f4:
        st.markdown('<div class="sg-card"><b>Online</b><br><br><b>WAITING FOR RECOVERY</b></div>', unsafe_allow_html=True)
else:
    st.success(f"Store #{selected.store_id} · {selected.mode.value} · {selected.health.value}")

st.divider()
render_incident_timeline(st.session_state.events)
st.divider()
st.subheader("Audit trail")
if st.session_state.events:
    rows = [
        {"Time": e.timestamp, "Event": e.event_type, "Status": e.status, "Message": e.message}
        for e in st.session_state.events
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.caption("Control-plane and StoreGuard events will be rendered here as an immutable incident narrative.")
