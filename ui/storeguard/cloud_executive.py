"""Read-only executive account of the verified StoreGuard one-trigger exercise.

Do not confuse an authenticated private Cloud Run service with a public health check.
No jobs, orders, approvals, or infrastructure changes are initiated here.
"""
from __future__ import annotations

import streamlit as st
from ui.storeguard.cloud_demo_backend import EXPOSED, get_events, grouped_runs, summarize

st.title('🛡️ StoreGuard | Executive Overview')
st.caption('Enterprise agent governance · simulated weather and primary-client outage · real governed cloud transaction')

try:
    runs = grouped_runs(get_events())
except Exception as exc:
    st.error(f'Cloud evidence is unavailable ({type(exc).__name__}). Verify application credentials and Firestore access.')
    st.stop()

if not runs:
    st.warning('No StoreGuard one-trigger evidence was found. No recovery claim can be made.')
    st.stop()

verified = [(rid, items, summarize(items)) for rid, items in runs if summarize(items)['verified']]
latest_rid, latest_events = runs[0]
latest_summary = summarize(latest_events)

if not verified:
    st.warning('Event records exist, but no run has a verified recovery receipt.')
    st.info('Review the Live Tornado & DR Demo page for run details; this executive page is read-only.')
    st.stop()

run_id, events, summary = verified[0]
if latest_rid != run_id:
    if latest_summary['verified']:
        st.info('Displaying the most recent verified demonstration.')
    else:
        st.warning('A newer run is incomplete or unverified. Displaying the latest previously verified run; do not treat these values as the newer run’s outcome.')

st.subheader('Executive snapshot')
a, b, c, d = st.columns(4)
a.metric('Fictional stores monitored', 40)
b.metric('Simulated stores in storm path', len(summary['exposed']))
c.metric('Completed governed actions', len(summary['agents']))
d.metric('Recovery transaction receipt', 'VERIFIED')
st.caption(f'Verified demonstration run: {run_id}')

st.success('A cryptographically signed synthetic order was acknowledged by the recovery service, and the operational Firestore receipt was independently verified by the job.')
st.info('The tornado and primary-client outage were simulated. There was NO actual primary cloud outage, store-state recovery, or human recovery approval.')

st.subheader('Regional transaction evidence')
left, right = st.columns(2)
with left:
    st.markdown('**Primary region · us-central1**')
    st.write('Primary-client request intentionally skipped for this simulated outage.')
    st.caption('This is not an independent live health measurement of the private primary service.')
with right:
    st.markdown('**Recovery region · us-east4**')
    order = (summary['receipt'].get('order') or {})
    st.write('Signed synthetic order: **ACKNOWLEDGED**')
    st.write('Operational ledger receipt: **VERIFIED**')
    st.code(str(order.get('receipt_id') or 'Receipt identifier unavailable'), language=None)

st.subheader('Agent identity and accountability')
for agent in summary['agents']:
    agent_name = agent.get('agent_id', 'Unknown agent')
    action = agent.get('action', 'Action not recorded')
    with st.expander(f'{agent_name} · {action}', expanded=True):
        st.write('Investigated store:', agent.get('store_id', 'Not recorded'))
        st.write('Action execution:', agent.get('action_run_id', 'Not recorded'))
        st.write('Fresh authorization:', agent.get('authorization_run_id', 'Not recorded'))
        st.write('Protected action gate:', agent.get('action_gate_run_id', 'Not recorded'))

st.subheader('Six-store simulated exposure')
exposed = set(summary['exposed'])
if exposed != set(EXPOSED):
    st.warning('Exposure evidence differs from the expected six-store scenario; inspect the underlying run.')
st.dataframe([
    {'Store': sid,
     'Storm exposure': 'SIMULATED' if sid in exposed else 'NOT RECORDED',
     'Governed investigation': 'Weather + SRE' if sid == 'SG-002' and len(summary['agents']) == 2 else 'Not executed',
     'Recovery approval': 'NOT GIVEN'}
    for sid in EXPOSED
], hide_index=True, use_container_width=True)

st.caption('Signed-order client 1802 is a separate enrolled identity from incident store SG-002. Private Cloud Run service health is not asserted by this evidence view.')
