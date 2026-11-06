"""Cloud-managed persistent rehearsal; no live signed orders in this release."""
import streamlit as st
import requests
from ui.storeguard.cloud_control_client import call

st.title('🌪️ StoreGuard | Governed DR Command Center')
st.warning('SIMULATION ONLY: actions below do not submit signed orders or execute agents.')
if 'sg_control_id' not in st.session_state:
    st.session_state.sg_control_id = ''
if st.button('Create a new governed DR rehearsal', type='primary'):
    try:
        st.session_state.sg_control_id = call('POST', '/exercises')['id']
    except Exception:
        st.error('Could not create exercise. Confirm IAM and control service health.')
if st.session_state.sg_control_id:
    exercise_id = st.session_state.sg_control_id
    try:
        state = call('GET', f'/exercises/{exercise_id}')
    except Exception:
        st.error('Unable to retrieve exercise. Please check Cloud Run logs.')
        st.stop()
    labels = ('NORMAL','PROTECTED','PRIMARY ROUTE FAULT','RECOVERY ROUTED','OPERATOR REVIEW REQUIRED','NORMAL RESTORED')
    st.subheader(f'Current state: {labels[state["phase"]]}')
    st.caption(f'Exercise: {exercise_id} · version {state["version"]} · persistence: Firestore')
    actions = [('start','▶ Start tornado'),('route_fault','⚠ Simulate primary route failure'),('recover','↪ Simulate recovery route'),('request_review','👤 Request operator review (not approval)'),('complete_checks','✓ Complete simulated checks')]
    for i,(action,label) in enumerate(actions):
        if st.button(label, key=action, disabled=state['phase'] != i):
            try:
                call('POST', f'/exercises/{exercise_id}/commands', {'action': action,'expected_version': state['version']})
                st.rerun()
            except requests.HTTPError:
                st.error('Command rejected or stale. Refresh to load current state.')
            except Exception:
                st.error('Command service unavailable.')
    st.subheader('Auditable simulation events')
    st.dataframe(state['events'], use_container_width=True)
    st.caption('No operator identity proof or agent workload verification is asserted by this simulated service.')
