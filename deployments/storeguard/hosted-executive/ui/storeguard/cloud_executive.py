"""Read-only executive account of the verified StoreGuard one-trigger exercise.

Do not confuse an authenticated private Cloud Run service with a public health check.
No jobs, orders, approvals, or infrastructure changes are initiated here.
"""
from __future__ import annotations

import streamlit as st
from ui.storeguard.cloud_demo_backend import EXPOSED, get_events, grouped_runs, summarize

st.title('🛡️ StoreGuard | Executive Overview')
st.caption('Enterprise agent governance · normal exercise baseline · real audited historical DR evidence')

st.subheader('Current operating picture — simulation baseline')
@st.fragment(run_every='6s')
def active_exercise_snapshot():
    active = bool(st.session_state.get('sg_cloud_awaiting_result'))
    exposed_count = 0
    if active:
        try:
            current_runs = grouped_runs(get_events())
            before = set(st.session_state.get('sg_cloud_before_run_ids', []))
            fresh = next((summarize(items) for rid, items in current_runs if rid not in before), None)
            if fresh:
                exposed_count = len(fresh['exposed'])
                if fresh['verified']:
                    st.session_state.sg_cloud_awaiting_result = False
                    active = False
            if active:
                st.info('Simulated exercise underway. Vault-governed actions are recorded as they execute.')
        except Exception as exc:
            st.warning(f'Exercise status temporarily unavailable ({type(exc).__name__})')
    a,b,c,d=st.columns(4)
    a.metric('Stores monitored', 40)
    b.metric('Currently affected', exposed_count if active else 0)
    c.metric('Active demo incidents', 1 if active else 0)
    d.metric('Exercise state', 'IN PROGRESS' if active else 'NORMAL')
    st.caption('NORMAL is the fictional demonstration baseline, not live physical-store telemetry. Historical incidents do not change the current state.')
active_exercise_snapshot()
st.divider()

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

st.subheader('Most recent VERIFIED exercise — historical evidence')
a, b, c, d = st.columns(4)
a.metric('Stores in exercise fleet', 40)
b.metric('Exposed in this past exercise', len(summary['exposed']))
c.metric('Governed actions in past exercise', len(summary['agents']))
d.metric('Recovery transaction receipt', 'VERIFIED')
st.caption(f'Verified demonstration run: {run_id}')

st.success('A cryptographically signed synthetic order was acknowledged by the recovery service, and the operational Firestore receipt was independently verified by the job.')
st.info('The tornado and primary-client outage were simulated. There was NO actual primary cloud outage, store-state recovery, or human recovery approval.')

from ui.storeguard.cloud_dr_visual import show_regional_dr_path
show_regional_dr_path(summary, run_id=run_id)

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

st.subheader('Vault-governed agent identity and accountability')
st.caption('Controls are evaluated on each agent run and protected action, and recorded in Firestore. These records demonstrate repeated verification—not independent continuous security monitoring.')
for agent in summary['agents']:
    agent_name = agent.get('agent_id', 'Unknown agent')
    action = agent.get('action', 'Action not recorded')
    with st.expander(f'{agent_name} · {action}', expanded=True):
        st.write('Investigated store:', agent.get('store_id', 'Not recorded'))
        st.write('Action execution:', agent.get('action_run_id', 'Not recorded'))
        st.write('Fresh authorization:', agent.get('authorization_run_id', 'Not recorded'))
        st.write('Protected action gate:', agent.get('action_gate_run_id', 'Not recorded'))
        st.write('Credential lifecycle:', 'Vault authenticated at execution boundary; short-lived token revoked after use (verified in prior Cloud Run execution logs)')

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


st.info('To launch a NEW simulated incident, select **Live Tornado & DR Demo** in the sidebar. The latest verified historical receipt remains available independently of the current exercise baseline.')
