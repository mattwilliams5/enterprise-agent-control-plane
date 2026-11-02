"""Agent passport and read-only investigation history."""
import streamlit as st
from ui.storeguard.governance_data import registry_rows, vault_health
from ui.storeguard.identity_display import audit_events, latest_run

st.title('Agent Identity & Activity')
st.caption('Registration metadata and recorded execution evidence are shown separately.')
rows = registry_rows()
if not rows:
    st.info('No agents registered.')
else:
    selected = st.selectbox('Select agent', [r['manifest']['agent_id'] for r in rows])
    row = next(r for r in rows if r['manifest']['agent_id'] == selected)
    manifest = row['manifest']
    st.subheader('Agent Passport')
    st.write(f"**Agent ID:** `{selected}`")
    st.write(f"**Registration SHA-256:** `{row['fingerprint']}`")
    st.caption('Local manifest fingerprint; not a signed attestation or workload proof.')
    st.write(f"**Owner:** {manifest['owner']} · **Purpose:** {manifest['purpose']}")
    st.write(f"**Approval:** {'Approved' if manifest['approved'] else 'Not approved'} · **Status:** {manifest['status']}")
    st.write(f"**Configured Vault entity binding:** `{manifest['vault_entity_id'] or 'Not configured'}`")
    with st.expander('Registration manifest'):
        st.json(manifest)
    with st.expander('Vault connectivity'):
        health = vault_health()
        st.write(f"{health['status']} — {health['detail']}")
        st.caption(f"Checked {health['checked']} UTC")

    st.subheader('Recorded execution history')
    events = audit_events(selected)
    if not events:
        st.info('No matching events in the local development audit database.')
    else:
        run_id, run_events = latest_run(events)
        entity = next((e['vault_entity_id'] for e in run_events if e['vault_entity_id']), None)
        st.write(f'**Latest recorded run:** `{run_id}`')
        st.write(f'**Vault entity verified during run (recorded):** `{entity or "Not recorded"}`')
        st.write(f"**Latest recorded lifecycle event:** `{run_events[0]['event_type']}`")
        st.caption('Historical records only; no claim of a currently authenticated session.')
        st.dataframe(events, use_container_width=True, hide_index=True)
        st.caption('SQLite development audit is not tamper-resistant or production-grade.')
