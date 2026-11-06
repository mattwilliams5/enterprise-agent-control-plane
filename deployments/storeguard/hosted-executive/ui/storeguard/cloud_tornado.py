"""One-click StoreGuard IAP-protected operator dashboard, with verified evidence."""
import json
import streamlit as st

from ui.storeguard.cloud_demo_backend import (
    EXPOSED, get_events, get_agent_decisions, get_latest_execution,
    grouped_runs, operator_trigger_configured, get_tool_events, run_demo, summarize,
)

st.title('🌪️ StoreGuard | Tornado & DR Exercise')
st.caption('SIMULATED tornado and client-side primary outage · REAL Vault-governed agents and signed recovery transaction')

if 'sg_cloud_operation' not in st.session_state:
    st.session_state.sg_cloud_operation = ''
if 'sg_cloud_awaiting_result' not in st.session_state:
    st.session_state.sg_cloud_awaiting_result = False
if 'sg_cloud_before_run_ids' not in st.session_state:
    st.session_state.sg_cloud_before_run_ids = []

st.subheader('Incident command')
st.info('One operator click launches the existing governed Cloud Run job. No store recovery, human approval, or cloud outage is performed.')
local = operator_trigger_configured()
if not local:
    st.warning('Operator launch unavailable: this deployment is not configured behind the required authenticated access boundary.')

col1, col2 = st.columns([2, 1])
with col1:
    launch = st.button('▶ Run tornado DR demo', type='primary', use_container_width=True,
                       disabled=not local or st.session_state.sg_cloud_awaiting_result)
with col2:
    if st.button('↻ Refresh evidence', use_container_width=True):
        st.rerun()

if launch:
    try:
        st.session_state.sg_cloud_before_run_ids = [rid for rid, _ in grouped_runs(get_events())]
        operation = run_demo()
        name = operation.get('name', '')
        if not name:
            raise RuntimeError('Cloud Run response has no operation identifier')
        st.session_state.sg_cloud_operation = name
        st.session_state.sg_cloud_awaiting_result = True
        st.rerun()
    except Exception as exc:
        st.error(f'Cloud launch failed: {type(exc).__name__}: {exc}')
        st.info('No automatic retry. Check permissions, recent executions, and delegation expiry.')

@st.fragment(run_every='6s')
def live_evidence():
    """Refresh both operation status and Firestore evidence without a terminal."""
    operation_name = st.session_state.sg_cloud_operation
    if operation_name and st.session_state.sg_cloud_awaiting_result:
        try:
            execution = get_latest_execution()
            if execution:
                status = 'COMPLETED' if execution.get('completionTime') else 'RUNNING / PROVISIONING'
                if execution.get('failedCount') or execution.get('cancelledCount'):
                    status = 'FAILED'
                st.write(f"**Cloud execution:** `{execution.get('name', 'unknown')}` · **{status}**")
                if status == 'FAILED':
                    st.error('The cloud task failed. Inspect logs before any retry.')
                    st.session_state.sg_cloud_awaiting_result = False
                elif status == 'COMPLETED':
                    st.info('Execution finished. Checking Firestore for a verified receipt.')
            else:
                st.info('Cloud Run has accepted the job request; awaiting execution metadata.')
        except Exception as exc:
            st.warning(f'Job status temporarily unavailable ({type(exc).__name__}); no retry will be made.')
    try:
        grouped = grouped_runs(get_events())
    except Exception as exc:
        st.error(f'Cannot read StoreGuard evidence: {type(exc).__name__}. Verify Google ADC and Firestore access.')
        return
    st.divider()
    st.subheader('Verified cloud demonstration evidence')
    if not grouped:
        st.warning('No cloud demo events found. No successful transaction is being claimed.')
        return
    before = set(st.session_state.sg_cloud_before_run_ids)
    new_ids = [run_id for run_id, _ in grouped if run_id not in before]
    if st.session_state.sg_cloud_awaiting_result and new_ids:
        new_run_id = new_ids[0]
        fresh = next(items for rid, items in grouped if rid == new_run_id)
        if summarize(fresh)['verified']:
            st.session_state.sg_cloud_awaiting_result = False
            st.session_state.sg_cloud_operation = ''
            st.session_state.sg_cloud_selected_run = new_run_id
            st.success('New cloud run: agents completed and signed recovery receipt verified.')
    elif st.session_state.sg_cloud_awaiting_result:
        st.info('Watching Firestore for this execution’s evidence. It will appear automatically as agents finish.')
    selected = st.selectbox('Demo run', [run_id for run_id, _ in grouped],
                            format_func=lambda value: value[:12] + '…',
                            key='sg_cloud_selected_run')
    events = next(items for rid, items in grouped if rid == selected)
    summary = summarize(events)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Stores monitored', 40)
    m2.metric('Simulated storm exposure', len(summary['exposed']))
    m3.metric('Completed governed agents', len(summary['agents']))
    m4.metric('Recovery receipt', 'VERIFIED' if summary['verified'] else 'NOT VERIFIED')
    from ui.storeguard.cloud_story import show_story
    show_story(summary, events, run_id=selected)
    st.subheader('Storm exposure · six fictional stores')
    st.caption('SG-002 is the only store with scoped live agent delegations. No store mode was changed.')
    exposed = set(summary['exposed'])
    if exposed and exposed != set(EXPOSED):
        st.error('Exposure evidence does not match the expected scenario.')
    st.dataframe([{'Store': store, 'Simulated tornado exposure': 'YES' if store in exposed else 'NOT RECORDED',
                   'Governed investigation': 'Weather + SRE' if store == 'SG-002' and len(summary['agents']) == 2 else 'Not executed',
                   'Recovery approval': 'NOT GIVEN'} for store in EXPOSED],
                 hide_index=True, use_container_width=True)
    st.subheader('Identity → Authorization → Action → Outcome')
    agent_ids = set()
    for agent in summary['agents']:
        with st.expander(f"{agent.get('agent_id', 'Unknown agent')} · {agent.get('action', '')}", expanded=True):
            st.write('Action execution:', agent.get('action_run_id', 'Not recorded'))
            st.write('Fresh authorization:', agent.get('authorization_run_id', 'Not recorded'))
            st.write('Protected action gate:', agent.get('action_gate_run_id', 'Not recorded'))
            st.write('Investigation store:', agent.get('store_id', 'Not recorded'))
        agent_ids.update(str(agent.get(k, '')) for k in ('authorization_run_id', 'action_gate_run_id'))
    if agent_ids:
        try:
            decisions = [row for row in get_agent_decisions() if str(row.get('run_id')) in agent_ids]
            if decisions:
                st.dataframe(decisions, hide_index=True, use_container_width=True)
            else:
                st.warning('Detailed agent decision records not found in the query window.')
        except Exception as exc:
            st.warning(f'Decision audit currently inaccessible: {type(exc).__name__}')
    st.subheader('Vault security and monitored actions')
    st.caption('This is persisted per-run governance evidence, NOT continuous out-of-band monitoring.')
    if agent_ids:
        try:
            # Action IDs are distinct from authorization IDs. Build from the verified agent records.
            action_ids = {str(a.get('action_run_id', '')) for a in summary['agents']}
            related_tools = [e for e in get_tool_events() if str(e.get('action_run_id', '')) in action_ids]
            if related_tools:
                st.dataframe([{'Agent':e.get('agent_id'), 'Event':e.get('event_type'),
                              'Action':e.get('action'), 'When':e.get('timestamp')}
                             for e in sorted(related_tools,key=lambda x:str(x.get('timestamp','')))],
                             hide_index=True, use_container_width=True)
            else:
                st.info('No tool audit events found in the recent query window.')
        except Exception as exc:
            st.warning(f'Tool audit temporarily unavailable ({type(exc).__name__})')
    st.info('Vault validates fresh Google workload identity and short-lived credentials. StoreGuard enforces delegation, scope and revocation checks on each action, and records the authorization/tool decisions. Do not interpret this as continuous independent security monitoring.')
    st.subheader('Real signed DR transaction')
    if summary['verified']:
        receipt = summary['receipt']
        order = receipt.get('order') or {}
        st.success('Recovery service acknowledged the signed synthetic order; Firestore receipt independently verified.')
        st.write('Recovery routing:', order.get('region', 'not recorded'))
        st.write('Order signing client:', order.get('transaction_store_id', '1802 (enrolled client)'))
        st.write('Operational incident store:', receipt.get('store_id', 'not recorded'))
        st.code(str(order.get('receipt_id', 'not recorded')))
    else:
        st.warning('This run has not recorded a verified recovery receipt.')
    with st.expander('Full persisted event timeline'):
        for event in sorted(events, key=lambda e: str(e.get('timestamp', ''))):
            st.write(event.get('timestamp', ''), '·', event.get('event_type', ''))
            st.code(json.dumps(event.get('detail') or {}, indent=2, default=str), language='json')
    st.caption('Simulation scope: fictional weather and client-side primary outage. Neither real failover infrastructure nor store-state recovery is asserted.')

live_evidence()
