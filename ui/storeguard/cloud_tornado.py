"""Cloud-safe interactive tornado and disaster-recovery rehearsal.

Simulation only: no Vault credentials, Firestore writes, order API
mutations, or privileged agent execution.
"""
import streamlit as st

st.title("🌪️ StoreGuard | Tornado & DR Exercise")
st.caption(
    "INTERACTIVE SIMULATION — Scenario transitions are not live "
    "infrastructure actions. Verified cloud evidence is on Executive Overview."
)

KEY = "sg_cloud_rehearsal"

def initial():
    return {
        "phase": 0,
        "paused": False,
        "events": ["Scenario initialized — all 40 stores NORMAL"],
    }

if KEY not in st.session_state:
    st.session_state[KEY] = initial()

s = st.session_state[KEY]

phases = [
    "NORMAL",
    "PROTECTED",
    "MAINTENANCE — PRIMARY ROUTE FAULT",
    "RECOVERY — QUEUE DRAINED",
    "RECOVERY — HUMAN APPROVED",
    "NORMAL — CHECKS COMPLETE",
]

def advance(expected, event):
    if s["phase"] == expected and not s["paused"]:
        s["phase"] += 1
        s["events"].append(event)

st.subheader("Incident command")

a, b, c = st.columns(3)
with a:
    if st.button("▶ Start tornado demo", use_container_width=True,
                 disabled=s["phase"] != 0):
        advance(0, "Tornado warning: exposed stores enter PROTECTED")
with b:
    if st.button("⏸ Pause" if not s["paused"] else "▶ Resume",
                 use_container_width=True,
                 disabled=s["phase"] in (0, 5)):
        s["paused"] = not s["paused"]
with c:
    if st.button("↺ Reset", use_container_width=True):
        st.session_state[KEY] = initial()
        st.rerun()

st.markdown(f"### Current state: {phases[s['phase']]}")

if s["paused"]:
    st.warning("Scenario paused — transitions are disabled.")

st.divider()
st.subheader("Disaster recovery controls")

if st.button("⚠ Simulate primary route failure", use_container_width=True,
             disabled=s["phase"] != 1 or s["paused"]):
    advance(1, "Primary route failure simulated; 20 orders queued")

if st.button("↪ Simulate recovery routing and queue drain",
             use_container_width=True,
             disabled=s["phase"] != 2 or s["paused"]):
    advance(2, "20 queued orders recovered via simulated recovery route")

if st.button("👤 Simulate operator recovery approval",
             use_container_width=True,
             disabled=s["phase"] != 3 or s["paused"]):
    advance(3, "Simulated human approval granted for recovery")

if st.button("✓ Complete simulated recovery checks",
             use_container_width=True,
             disabled=s["phase"] != 4 or s["paused"]):
    advance(4, "Recovery checks simulated; stores returned to NORMAL")

st.divider()
st.subheader("Exercise telemetry")

phase = s["phase"]
primary = 20 if phase >= 2 else 0
queued = 20 if phase == 2 else 0
recovered = 20 if phase >= 3 else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Stores monitored", 40)
m2.metric("Simulated primary orders", primary)
m3.metric("Simulated queue pending", queued)
m4.metric("Simulated recovered orders", recovered)

st.subheader("Store network")
stores = []
for store_id in range(1800, 1840):
    exposed = store_id < 1812
    state = "NORMAL"
    if exposed and phase in (1, 2):
        state = "PROTECTED" if phase == 1 else "MAINTENANCE"
    elif exposed and phase in (3, 4):
        state = "RECOVERY"
    stores.append({
        "Store": str(store_id),
        "Exposure": "In simulated tornado path" if exposed else "Outside path",
        "State": state,
    })
st.dataframe(stores, use_container_width=True, hide_index=True)

st.subheader("Exercise event timeline")
for event in reversed(s["events"]):
    st.write("•", event)

st.info(
    "This page is a deterministic rehearsal. It does not submit orders, "
    "cause an outage, issue Vault credentials, or execute AI agents. "
    "See Executive Overview for evidence from the previously verified "
    "40-store cloud recovery test."
)
