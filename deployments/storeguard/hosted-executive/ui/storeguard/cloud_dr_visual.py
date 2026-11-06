"""Evidence-driven regional DR visualization.

Never interpret simulated outage evidence as actual infrastructure failure.
"""
from __future__ import annotations


def regional_evidence(summary: dict) -> dict:
    receipt = summary.get("receipt") or {}
    order = receipt.get("order") or {}
    attempts = order.get("attempts") or []

    primary_simulated = any(
        isinstance(a, dict)
        and a.get("region") == "primary"
        and a.get("error") == "SIMULATED_CLIENT_SIDE_OUTAGE"
        for a in attempts
    )

    recovery_200 = any(
        isinstance(a, dict)
        and a.get("region") == "recovery"
        and a.get("status_code") == 200
        for a in attempts
    )

    verified = (
        summary.get("verified") is True
        and receipt.get("status") == "recovery_transaction_verified"
        and order.get("outcome") == "acknowledged"
        and order.get("region") == "recovery"
        and bool(order.get("receipt_id"))
        and recovery_200
    )

    governed = [
        agent for agent in summary.get("agents", [])
        if isinstance(agent, dict)
        and agent.get("agent_id")
        and agent.get("authorization_run_id")
        and agent.get("action_gate_run_id")
        and agent.get("action_run_id")
    ]

    return {
        "primary_simulated": primary_simulated,
        "recovery_200": recovery_200,
        "verified": verified,
        "receipt_id": order.get("receipt_id") if verified else None,
        "store_client": receipt.get("transaction_store_id"),
        "governed_agents": governed,
    }


def show_regional_dr_path(summary: dict, *, run_id: str) -> None:
    import streamlit as st

    evidence = regional_evidence(summary)

    st.subheader("Regional DR | Verified evidence path")
    st.caption(
        f"Historical exercise: {run_id}. "
        "This is recorded demonstration evidence, not live regional health."
    )

    primary, vault, recovery, ledger = st.columns(4)

    with primary:
        st.markdown("**1. Primary region**")
        st.caption("us-central1")
        if evidence["primary_simulated"]:
            st.warning("Client outage SIMULATED")
        else:
            st.info("No outage evidence")

    with vault:
        st.markdown("**2. Vault + StoreGuard**")
        st.caption("Identity and action governance")
        st.metric(
            "Governed actions",
            len(evidence["governed_agents"])
        )

    with recovery:
        st.markdown("**3. Recovery region**")
        st.caption("us-east4")
        if evidence["recovery_200"]:
            st.success("Order HTTP 200")
        else:
            st.warning("Not acknowledged")

    with ledger:
        st.markdown("**4. Firestore ledger**")
        st.caption("Operational database")
        if evidence["verified"]:
            st.success("Receipt VERIFIED")
        else:
            st.warning("NOT VERIFIED")

    if evidence["primary_simulated"] and evidence["verified"]:
        st.success(
            "Verified: signed transaction continuity "
            "through the recovery region."
        )
        st.code(evidence["receipt_id"])
        st.caption(
            f"Enrolled transaction client: "
            f"{evidence['store_client']}"
        )
    else:
        st.warning(
            "This run does not establish a complete "
            "verified DR transaction path."
        )

    with st.expander("Vault-governed agent accountability"):
        if evidence["governed_agents"]:
            st.dataframe(
                [
                    {
                        "Agent": a["agent_id"],
                        "Action": a.get("action"),
                        "Authorization": a["authorization_run_id"],
                        "Protected gate": a["action_gate_run_id"],
                    }
                    for a in evidence["governed_agents"]
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.warning("Complete authorization evidence unavailable")

        st.caption(
            "Agent authorizations are recorded per action. "
            "Vault authentication and credential revocation "
            "are corroborated by Cloud Run execution logs. "
            "This is not independent 24/7 monitoring."
        )

    st.info(
        "Exercise scope: fictional tornado, simulated primary-client "
        "outage, and real recovery-region transaction. "
        "No actual regional outage or store recovery performed."
    )
