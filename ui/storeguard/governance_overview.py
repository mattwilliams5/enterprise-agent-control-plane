"""Executive governance overview; read-only registry and Vault health."""
import streamlit as st
from ui.storeguard.governance_data import registry_rows, vault_health

st.title("🛡️ Agent Governance Overview")
st.caption("Secure Autonomy · Complete Accountability")
rows = registry_rows()
approved = sum(1 for row in rows if row["manifest"]["approved"] and row["manifest"]["status"] == "active")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Registered agents", len(rows))
c2.metric("Approved & active", approved)
c3.metric("Verified executions", "Not available")
c4.metric("Unattributed actions", "Unknown")
st.subheader("Security infrastructure")
if st.button("Refresh Vault health", key="refresh_vault"):
    pass
health = vault_health()
st.write(f"**HashiCorp Vault:** {health['status']}")
st.caption(f"{health['detail']} · Checked {health['checked']} UTC · {health['address']}")
st.info("Vault connectivity does not prove agent identity or authorization. Live execution evidence and persistent audit are not yet integrated.")
st.subheader("Agent registry")
st.dataframe([{
    "Agent": r["manifest"]["agent_id"],
    "Owner": r["manifest"]["owner"],
    "Approval": "Approved" if r["manifest"]["approved"] else "Not approved",
    "Status": r["manifest"]["status"],
    "Registration SHA-256": r["fingerprint"][:16] + "…",
    "Run identity proof": "Not verified",
} for r in rows], width="stretch", hide_index=True)
st.caption("Registration fingerprints are calculated from current local metadata; they are not signed registration attestations.")
st.subheader("Agent activity & exceptions")
st.warning("No trusted, persistent execution audit feed connected. Do not infer zero incidents or zero unauthorized actions.")
