"""StoreGuard v0.9.2 split command center.

Presentation only. Incident controller, Vault gate, audit persistence and DR
simulation are owned by the existing application and are not modified here.
"""
from datetime import datetime, timezone
import streamlit as st


def _value(item, field, default=""):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _event_rows(events, audit):
    rows = []
    for e in events[-70:]:
        rows.append({
            "Time (UTC)": str(_value(e, "timestamp")),
            "Source": "Simulated operations",
            "Event": str(_value(e, "event_type")),
            "Run": "—",
        })
    for e in audit[-150:]:
        rows.append({
            "Time (UTC)": str(e.get("timestamp", "")),
            "Source": "Application audit",
            "Event": str(e.get("event_type", "")),
            "Run": str(e.get("run_id", "")),
        })
    return sorted(rows, key=lambda r: r["Time (UTC)"], reverse=True)


def _security_panel(incident, audit, agent_name):
    st.markdown("**🔐 Agent Security · Live Evidence**")
    st.caption(f"Agent: `{agent_name}` · Incident-specific application audit")
    if not incident:
        st.info("No incident started. Security evidence is pending.")
        return
    run_ids = list(dict.fromkeys(str(e.get("run_id")) for e in audit if e.get("run_id")))
    if not run_ids:
        st.warning("No correlated agent run evidence yet; authorization not assumed.")
        return
    selected = st.selectbox("Execution run", list(reversed(run_ids)), key="sg_v092_run")
    records = [e for e in audit if str(e.get("run_id")) == selected]
    types = {str(e.get("event_type", "")) for e in records}
    if types & {"DENIED", "UNREGISTERED"}:
        st.error("Authorization: denied / agent unregistered (recorded)")
    elif "AUTHORIZED" in types:
        st.success("Authorization: recorded as allowed")
    else:
        st.warning("Authorization: no decision recorded")
    if types & {"FAILED", "EXECUTION_FAILED"}:
        st.error("Execution: failure recorded")
    elif "COMPLETED" in types:
        st.success("Execution: completed (recorded)")
    elif "STARTED" in types:
        st.info("Execution: started")
    else:
        st.warning("Execution: pending")
    if "REVOCATION_FAILED" in types:
        st.error("Credential closure: REVOCATION FAILED")
    elif "TOKEN_REVOKED" in types:
        st.success("Credential closure: revocation recorded")
    else:
        st.warning("Credential closure: not evidenced")
    st.caption("These are local application records, not independently verified Vault server audit logs.")



def _trace_panel(events, audit, latest):
    st.markdown("**🔎 Technical Evidence · Investigation Console**")
    selected_run = st.session_state.get("sg_v092_run")

    records = [
        e for e in audit
        if selected_run
        and str(e.get("run_id", "")) == str(selected_run)
    ]
    records.sort(key=lambda e: str(e.get("timestamp", "")))

    if not records:
        st.info("No security audit records for the selected execution.")
    else:
        entity_ids = {
            str(e.get("vault_entity_id"))
            for e in records
            if e.get("vault_entity_id")
        }
        types = {str(e.get("event_type", "")) for e in records}

        st.caption("Selected execution: " + str(selected_run))

        a, b, c = st.columns(3)
        a.metric("Audit events", len(records))
        b.metric("Vault entities", len(entity_ids))
        c.metric(
            "Credential closure",
            "Failed" if "REVOCATION_FAILED" in types
            else "Recorded" if "TOKEN_REVOKED" in types
            else "Pending",
        )

        st.markdown("**Execution timeline**")
        rows = []
        for e in records:
            timestamp = str(e.get("timestamp", ""))
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.astimezone(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
            except ValueError:
                pass

            rows.append({
                "UTC": timestamp,
                "Event": str(e.get("event_type", "")),
                "Reason": str(e.get("reason") or "Not recorded"),
            })

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Full investigation evidence", expanded=False):
            st.caption("Application-recorded evidence, not independent Vault audit.")
            for index, e in enumerate(records, 1):
                st.markdown(
                    f"**{index}. {e.get('event_type', 'Unknown')}**"
                )
                st.json({
                    "timestamp": e.get("timestamp"),
                    "event_type": e.get("event_type"),
                    "run_id": e.get("run_id"),
                    "vault_entity_id": e.get("vault_entity_id"),
                    "reason": e.get("reason"),
                })

    st.caption(
        "Evidence source: local application SQLite audit. "
        "Vault server audit correlation is not yet implemented."
    )

    with st.expander("Simulated operational timeline", expanded=False):
        operational_rows = _event_rows(events, [])
        if operational_rows:
            st.dataframe(
                operational_rows,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No operational events recorded.")

    if latest:
        with st.expander("Historical AI recommendation", expanded=False):
            st.write(str(latest[1].get("analysis", "No analysis returned.")))
            st.caption(
                "Historical advisory snapshot; may not describe the current store state."
            )


def render_compact_cockpit(*, store_id, phase, incident, controller, agent_name,
                           stages, events, audit, latest, ai_error):
    """One operational half; two permanently visible technical panels on the right."""
    # Never hide security failures, even if the detailed panel scrolls.
    if ai_error:
        st.error("Governed investigation failed. Inspect the Vault configuration and server logs.")
    if any(e.get("event_type") == "REVOCATION_FAILED" for e in audit):
        st.error("SECURITY ALERT: Token revocation failure recorded")
    if any(e.get("event_type") in ("DENIED", "UNREGISTERED") for e in audit):
        st.error("SECURITY ALERT: Agent execution denied or agent unregistered")

    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(border=True):
            st.markdown("**🏪 StoreGuard · Live Store Demonstration**")
            store = getattr(controller, "stores", {}).get(str(store_id)) if controller else None
            state = getattr(getattr(store, "state", None), "name", "UNKNOWN")
            st.markdown(f"**Store {store_id}** · State `{state}` · Phase `{getattr(phase, 'name', phase)}`")
            if incident:
                st.caption(f"Incident: `{_value(incident, 'incident_id', 'Unknown')}`")
            else:
                st.caption("Awaiting incident")
            a, b, c = st.columns(3)
            a.caption("🏬 Operations")
            b.caption("📦 Inventory")
            c.caption("💳 Payments")
            st.caption("Store condition and disaster recovery are simulated. Full Store Operations view remains in navigation.")
            if events:
                st.caption(f"Latest operational event: `{_value(events[-1], 'event_type', 'Unknown')}`")
            st.markdown("**Mission progression**")
            for name, status in stages:
                if status.startswith(("Complete", "Approved")):
                    mark = "🟢"
                elif status == "Failed":
                    mark = "🔴"
                elif status in ("Running", "Action required"):
                    mark = "🟠"
                else:
                    mark = "⚪"
                st.caption(f"{mark} **{name}** — {status}")
            st.caption("Start, pause, approval, verification and reset controls remain at the top of Mission Control.")

    with right:
        with st.container(border=True):
            _security_panel(incident, audit, agent_name)
        with st.container(border=True):
            _trace_panel(events, audit, latest)
