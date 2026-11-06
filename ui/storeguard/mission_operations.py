"""Mission Control: reuse original StoreGuard controller and scenario logic.

Vault governance applies to read-only AI investigation, not DR transitions.
"""
import json
import os
import time
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import requests
import streamlit as st
from applications.storeguard.ai_recovery_agent import run_recovery_agent
from applications.storeguard.scenario_integration import SCENARIO_HEALTH, build_local_scenario
from applications.storeguard.ai_investigation import snapshot_for_phase, executive_question
from applications.storeguard.governed_recovery import issue_demo_approval, execute_demo_approval, execute_post_recovery_checks
from applications.storeguard.controller import StoreGuardController
from applications.storeguard.scenario_orchestrator import Phase, ScenarioError
from applications.storeguard.state_machine import StoreState
from applications.storeguard.investigation_controller import InvestigationController, InvestigationRequest, AGENT_NAME
from ui.storeguard.demo_data import build_demo_stores, tornado_fixture
from ui.storeguard.view_models import AgentEventView, Health, StoreMode

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
    st.session_state.pop("sg_ai_failed_snapshot", None)
    st.session_state.pop("sg_v092_run", None)
    st.session_state.pop("sg_v092_observed_run", None)
    st.session_state.pop("sg_ai_queued_snapshot", None)
    st.session_state.pop("sg_ai_history", None)
    st.session_state.pop("sg_demo_approval", None)


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
    st.session_state.sg_ai_failed_snapshot = None
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
        st.session_state.sg_ai_failed_snapshot = None
        st.session_state.events.append(AgentEventView(
            "AI_INVESTIGATION_COMPLETE",
            f"Read-only AI advisory ready for store {snapshot.store_id} "
            f"using {snapshot.evidence_key} evidence", "complete"))
    except Exception as exc:
        st.session_state.sg_ai_error = str(exc)
        st.session_state.sg_ai_failed_snapshot = snapshot
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


# Replace only the read-only AI worker. The original scenario state machine,
# human approval, event collection and control logic remain unchanged.
VAULT_ADDR = os.getenv("STOREGUARD_VAULT_ADDR", "http://127.0.0.1:8200").rstrip("/")
TOKEN_FILE = Path("/tmp/storeguard-provisioner-token.json")
AUDIT_DB = os.getenv("STOREGUARD_AUDIT_DB", "data/storeguard_security_audit.sqlite3")
ALLOWED_STORE_IDS = frozenset(x.strip() for x in os.getenv("STOREGUARD_ALLOWED_STORE_IDS", "1847").split(",") if x.strip())


def _fresh_credentials():
    # Restricted provisioner only. Never use a Vault root token in this UI.
    token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["auth"]["client_token"]
    headers = {"X-Vault-Token": token}
    base = f"{VAULT_ADDR}/v1/auth/approle/role/storeguard-investigator"
    role = requests.get(f"{base}/role-id", headers=headers, timeout=8)
    role.raise_for_status()
    secret = requests.post(f"{base}/secret-id", headers=headers, json={}, timeout=8)
    secret.raise_for_status()
    return role.json()["data"]["role_id"], secret.json()["data"]["secret_id"]


def _investigate_snapshot(snapshot):
    if not TOKEN_FILE.is_file():
        raise RuntimeError("Restricted Vault provisioner token missing or expired; refresh it before running")
    controller = InvestigationController(
        vault_addr=VAULT_ADDR,
        credential_provider=_fresh_credentials,
        allowed_store_ids=ALLOWED_STORE_IDS,
        investigation_runner=run_recovery_agent,
        db_path=AUDIT_DB,
    )
    response = controller.investigate(InvestigationRequest(
        store_id=str(snapshot.store_id),
        incident_id=str(snapshot.incident_id),
        health=snapshot.health,
        elapsed_minutes=snapshot.elapsed_minutes,
        rto_minutes=30,
        question=executive_question(snapshot),
    ))
    result = dict(response["result"])
    result["governed_run_id"] = response["run_id"]
    return result


def ensure_mission_session():
    if "stores" not in st.session_state:
        st.session_state.stores = build_demo_stores()
    if "incident" not in st.session_state:
        st.session_state.incident = None
    if "events" not in st.session_state:
        st.session_state.events = []
    if "selected_store" not in st.session_state:
        st.session_state.selected_store = "1847"
    if "controller" not in st.session_state:
        st.session_state.controller = build_controller(st.session_state.stores)
