"""Read-only agent passport from registry metadata."""
import streamlit as st
from ui.storeguard.governance_data import registry_rows, vault_health

st.title("Agent Identity & Activity")
st.caption("Every agent shows ID. Every action is accountable.")
rows = registry_rows()
if not rows:
    st.info("No agents registered.")
else:
    selected = st.selectbox("Select agent", [r["manifest"]["agent_id"] for r in rows])
    row = next(r for r in rows if r["manifest"]["agent_id"] == selected)
    manifest = row["manifest"]
    st.subheader("Agent Passport")
    st.write(f"**Registration SHA-256:** `{row['fingerprint']}`")
    st.caption("Fingerprint of the current local manifest. Not a signed attestation or cryptographic workload proof.")
    st.write(f"**Owner:** {manifest['owner']} · **Purpose:** {manifest['purpose']}")
    st.write(f"**Approval:** {'Approved' if manifest['approved'] else 'Not approved'} · **Status:** {manifest['status']}")
    st.write(f"**Configured Vault entity binding:** `{manifest['vault_entity_id'] or 'Not configured'}`")
    st.write("**Live identity verification:** Not verified for a specific run")
    with st.expander("Registration manifest"):
        st.json(manifest)
    with st.expander("Vault connectivity"):
        health = vault_health()
        st.write(f"{health['status']} — {health['detail']}")
        st.caption(f"Checked {health['checked']} UTC")
    st.subheader("Execution history")
    st.info("No persistent trusted run audit connected yet. Run-level identity, intent, policy decisions, and outcomes cannot be confirmed here.")
