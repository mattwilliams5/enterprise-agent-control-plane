"""StoreGuard's safe, read-only Cloud Run executive preview.

This page is intentionally the ONLY imported cloud-mode page until privileged
agent and action operations have been moved behind an authorized backend.
"""
import os
import streamlit as st
from ui.storeguard.cloud_data import cloud_health, latest_runs

st.title('🛡️ StoreGuard | Enterprise Agent Governance')
st.caption('CLOUD EXECUTIVE PREVIEW · Live infrastructure, verified demo evidence · No privileged actions')

health_columns = st.columns(2)
for col, label, env in zip(health_columns, ['Primary · us-central1', 'Recovery · us-east4'],
                          ['STOREGUARD_PRIMARY_CLOUD_URL', 'STOREGUARD_RECOVERY_CLOUD_URL']):
    with col:
        st.subheader(label)
        outcome = cloud_health(env)
        if outcome['healthy']:
            st.success(outcome['detail'])
        else:
            st.error(outcome['detail'])

st.divider()
st.subheader('Verified disaster-recovery evidence')
st.caption('These results are operator-published summaries of tested runs, not a live regional outage.')
try:
    runs = latest_runs()
except Exception:
    st.warning('Verified cloud demo evidence is currently unavailable.')
    runs = []
if not runs:
    st.info('No verified demo run has been published. Cloud health checks alone do not prove transaction recovery.')
else:
    selected = runs[0]
    a,b,c,d = st.columns(4)
    a.metric('Primary commits', selected['primary_commits'])
    b.metric('Queued & recovered', f"{selected['recovered_commits']}/{selected['queued_during_outage']}")
    c.metric('Duplicate checks', selected['cross_region_duplicates'])
    d.metric('Replays rejected', selected['replays_rejected'])
    st.caption(f"Run {selected['run_id']} · {selected['completed_at']} · Pending: {selected['pending']}")
    with st.expander('Other verified run summaries'):
        st.dataframe(runs, hide_index=True)

st.divider()
with st.expander('Agent governance — cloud rollout boundary'):
    st.info('Live Vault-governed agents have been verified locally. Cloud agent authentication, execution and shared audit integration are not yet enabled in this hosted preview.')
with st.expander('Weather scenario — simulation disclosure'):
    st.info('Weather inputs are deterministic fictional scenarios, not a live weather forecast. Protected-mode changes require separate authorization and human review.')

st.caption('Order services remain IAM-authenticated. This page does not create orders, issue Vault tokens, or perform recovery actions.')
