"""Standalone governed StoreGuard AI investigation page.

Run from repository root:
  python -m streamlit run ui/storeguard/governed_analyst.py --server.port 8504

The original dashboard and human-controlled state machine are not modified.
"""

import json
import os
import uuid
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import streamlit as st

from applications.storeguard.ai_recovery_agent import run_recovery_agent
from applications.storeguard.investigation_controller import (
    InvestigationController,
    InvestigationRequest,
)
from applications.storeguard.recovery_agent import SystemHealth
from applications.storeguard.investigation_controller import AGENT_NAME

VAULT_ADDR = os.getenv("STOREGUARD_VAULT_ADDR", "http://127.0.0.1:8200").rstrip("/")
ROLE = "storeguard-investigator"
TOKEN_FILE = Path("/tmp/storeguard-provisioner-token.json")
AUDIT_DB = "data/storeguard_security_audit.sqlite3"
# Server-side authorization scope. UI selections NEVER expand this set.
ALLOWED_STORE_IDS = frozenset(
    item.strip() for item in os.getenv("STOREGUARD_ALLOWED_STORE_IDS", "1847").split(",")
    if item.strip()
)


def fresh_credentials():
    """Provision a single-use SecretID using a restricted provisioner token."""
    # This local demo reads a short-lived token; never use a root token here.
    provisioner = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["auth"]["client_token"]
    headers = {"X-Vault-Token": provisioner}
    role_url = f"{VAULT_ADDR}/v1/auth/approle/role/{ROLE}"
    role = requests.get(f"{role_url}/role-id", headers=headers, timeout=8)
    role.raise_for_status()
    secret = requests.post(f"{role_url}/secret-id", headers=headers, json={}, timeout=8)
    secret.raise_for_status()
    return role.json()["data"]["role_id"], secret.json()["data"]["secret_id"]


st.set_page_config(page_title="StoreGuard | Governed AI", page_icon="🛡️", layout="wide")
st.title("🛡️ StoreGuard | Governed AI Recovery Analyst")
st.caption(f"Agent ID: `{AGENT_NAME}` · Registered identity; verified per investigation")
st.caption("Vault-authorized, read-only AI investigation. Simulated health data; no recovery execution or state changes.")

if not ALLOWED_STORE_IDS:
    st.error("No authorized stores configured. Set STOREGUARD_ALLOWED_STORE_IDS on the server.")
    st.stop()

with st.sidebar:
    st.subheader("Governance boundary")
    st.write("**Identity:** Vault AppRole")
    st.write("**Authorization:** Server-side store allowlist")
    st.write("**Audit:** SQLite lifecycle events (development only)")
    st.write("**Credentials:** Short-lived, revoked after execution")
    st.warning("Demo only: local Vault and SQLite are not production security boundaries.")

store_id = st.selectbox("Authorized store", sorted(ALLOWED_STORE_IDS))
scenario = st.selectbox("Simulated diagnostic scenario", [
    "Connectivity and payments degraded", "Initial outage", "Partial restoration", "Services restored"
])
scenarios = {
    "Connectivity and payments degraded": (False, True, False, True, True),
    "Initial outage": (False, False, True, True, True),
    "Partial restoration": (True, False, True, True, True),
    "Services restored": (True, True, True, True, True),
}
health = SystemHealth(**dict(zip(
    ("connectivity", "inventory", "payments", "safety", "orders"), scenarios[scenario]
)))
cols = st.columns(5)
for col, (name, healthy) in zip(cols, health.model_dump().items()):
    col.metric(name.title(), "Healthy" if healthy else "Unhealthy")

elapsed = st.slider("Elapsed minutes", 0, 60, 8)
rto = st.number_input("Recovery-time objective (minutes)", min_value=1, max_value=240, value=30)
question = st.text_area("Investigation question", value=(
    "Identify observed failures, possible business risks, and recommended human next steps. "
    "Do not execute recovery or approve a state transition."
))

signature = (store_id, scenario, elapsed, rto, question)
if st.session_state.get("governed_signature") != signature:
    st.session_state.pop("governed_result", None)
    st.session_state.pop("governed_events", None)

# STOREGUARD_LIVE_SECURITY_V1
# Background worker NEVER calls Streamlit. The UI polls actual SQLite audit records.
@st.cache_resource
def _security_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="storeguard-investigation")


def _run_governed_investigation(request):
    controller = InvestigationController(
        vault_addr=VAULT_ADDR,
        credential_provider=fresh_credentials,
        allowed_store_ids=ALLOWED_STORE_IDS,
        investigation_runner=run_recovery_agent,
        db_path=AUDIT_DB,
    )
    return controller.investigate(request)


def _audit_for_incident(incident_id):
    """Return only events belonging to the current incident, never invented steps."""
    if not incident_id or not Path(AUDIT_DB).is_file():
        return []
    try:
        with sqlite3.connect(f"file:{Path(AUDIT_DB).resolve()}?mode=ro", uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT timestamp, run_id, agent, store_id, event_type, "
                "reason, vault_entity_id FROM execution_events "
                "WHERE incident_id=? ORDER BY timestamp, rowid",
                (incident_id,),
            )]
    except sqlite3.Error:
        return []


active_future = st.session_state.get("security_future")
active = active_future is not None and not active_future.done()

left, right = st.columns(2)
with left:
    start_requested = st.button(
        "🔍 Run Vault-governed investigation", type="primary", disabled=active,
    )
with right:
    deny_requested = st.button(
        "🛑 Demonstrate unauthorized request", disabled=active,
        help="Uses a deliberately out-of-scope store ID; no AI call or new credential should occur.",
    )

if start_requested or deny_requested:
    if start_requested and not question.strip():
        st.warning("Enter an investigation question.")
    elif start_requested and not TOKEN_FILE.is_file():
        st.error("Restricted provisioner token missing. Refresh the local demo provisioner token.")
    else:
        incident_id = f"ui-investigation-{uuid.uuid4().hex[:12]}"
        target_store = store_id if start_requested else "__unauthorized_demo__"
        # This ID is deliberately outside the trusted scope.
        assert not deny_requested or target_store not in ALLOWED_STORE_IDS
        request = InvestigationRequest(
            store_id=target_store,
            incident_id=incident_id,
            health=health,
            elapsed_minutes=elapsed,
            rto_minutes=int(rto),
            question=question.strip() if start_requested else "Unauthorized scope test",
        )
        st.session_state.security_incident_id = incident_id
        st.session_state.security_kind = "approved" if start_requested else "denied"
        st.session_state.security_future = _security_executor().submit(
            _run_governed_investigation, request
        )
        st.session_state.pop("governed_result", None)
        st.session_state.pop("governed_run_id", None)
        st.session_state.governed_signature = signature
        st.rerun()


@st.fragment(run_every="1s")
def live_security_lifecycle():
    st.divider()
    st.subheader("🔐 Live Agent Security Lifecycle")
    st.caption("Live evidence from the local SQLite audit; no simulated security progress or artificial delays.")
    st.write(f"**Agent ID:** `{AGENT_NAME}`")
    incident_id = st.session_state.get("security_incident_id")
    future = st.session_state.get("security_future")
    if not incident_id:
        st.info("Start an investigation to watch its real authorization and execution events.")
        return
    st.caption(f"Incident: {incident_id}")
    rows = _audit_for_incident(incident_id)
    event_names = [row["event_type"] for row in rows]
    run_id = rows[0]["run_id"] if rows else None
    entity_id = next((row["vault_entity_id"] for row in rows if row["vault_entity_id"]), None)
    st.write("**Run ID:** " + (f"`{run_id}`" if run_id else "Pending audit record"))
    st.write("**Vault entity ID (recorded):** " + (f"`{entity_id}`" if entity_id else "Not yet verified in audit"))

    if rows:
        for row in rows:
            st.write(f"`{row['timestamp']}` · **{row['event_type']}** — {row['reason']}")
    elif future is not None and not future.done():
        st.info("Investigation submitted. Awaiting first recorded security event…")
    else:
        st.info("No audit events recorded for this incident.")

    if future is not None and not future.done():
        st.info("Investigation in progress. This panel refreshes every second.")
        return

    if future is None:
        return

    try:
        response = future.result()
    except Exception as exc:
        # Never display exception text; Vault/HTTP errors may include sensitive details.
        if st.session_state.get("security_kind") == "denied" and "DENIED" in event_names:
            st.success("Out-of-scope investigation denied and recorded; no AI execution requested.")
        else:
            st.error("Investigation failed or was denied. Review audit events and sanitized server logs.")
        return

    if st.session_state.get("security_kind") == "denied":
        st.error("SECURITY CHECK FAILED: unauthorized request unexpectedly returned successfully.")
        return

    st.session_state.governed_result = response.get("result")
    st.session_state.governed_run_id = response.get("run_id")
    expected = ["AUTHORIZED", "STARTED", "COMPLETED", "TOKEN_REVOKED"]
    if event_names == expected:
        st.success("Vault-governed investigation completed; token revocation acknowledged.")
    else:
        st.warning("Investigation returned, but audit lifecycle needs review.")
    result = response.get("result") or {}
    if result.get("analysis"):
        st.subheader("AI recommendation — human review required")
        st.markdown(result["analysis"])
        st.caption("Advisory only. Recovery-state transitions require authorized human action.")


live_security_lifecycle()
