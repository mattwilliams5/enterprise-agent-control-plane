"""Read-only StoreGuard execution evidence, correlated by persisted demo_run_id."""
import streamlit as st

from ui.storeguard.cloud_demo_backend import (get_events, get_agent_decisions, get_tool_events, grouped_runs, summarize)
from ui.storeguard.cloud_story import action_audit_rows, event_rows, narrative

st.title('⌘ StoreGuard | Execution Monitor')
st.caption('Read-only persisted actions · same run ID as the executive view · refreshes every 6 seconds')
st.warning('These are recorded, allowlisted events—not a shell terminal, live service-health feed, or raw Vault audit log.')

@st.fragment(run_every='6s')
def monitor():
    try:
        groups = grouped_runs(get_events())
    except Exception as exc:
        st.error(f'Evidence unavailable: {type(exc).__name__}')
        return
    if not groups:
        st.info('No demonstration events are available.')
        return
    available = {run_id: events for run_id, events in groups}
    requested = st.query_params.get('run', '')
    run_id = requested if requested in available else groups[0][0]
    if requested and requested not in available:
        st.warning('The requested run is outside the current evidence window; showing the latest run.')
    run_id = st.selectbox('Exercise run', list(available),
                          index=list(available).index(run_id),
                          format_func=lambda value: value[:12] + '…',
                          key='sg_monitor_run')
    events = available[run_id]
    result = narrative(summarize(events), events)
    a, b, c = st.columns(3)
    a.metric('Governed actions with IDs', result['actions'])
    b.metric('Recovery HTTP 200', 'RECORDED' if result['regional_ack'] else 'NOT RECORDED')
    c.metric('Receipt', 'VERIFIED' if result['verified'] else 'NOT VERIFIED')
    st.code(f'run_id: {run_id}', language='text')
    rows = event_rows(events)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info('No allowlisted events have been recorded for this run.')
    st.subheader('Correlated protected actions and policy evidence')
    try:
        audits = action_audit_rows(summarize(events), get_tool_events(), get_agent_decisions())
    except Exception as exc:
        st.warning(f'Governance evidence temporarily inaccessible: {type(exc).__name__}')
        audits = []
    if audits:
        st.dataframe(audits, hide_index=True, use_container_width=True)
    else:
        st.info('No matching action or authorization audit records were available in the recent query window.')
    st.caption('Time in America/New_York (EST/EDT). UTC is retained for correlation.')
    st.info('Vault authenticates workloads and manages credentials; StoreGuard authorizes protected actions. Token issuance/revocation is not independently proved by these event rows.')

monitor()
