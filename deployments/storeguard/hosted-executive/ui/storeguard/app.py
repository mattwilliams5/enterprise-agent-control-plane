"""Hosted StoreGuard executive navigation, no local simulator imports."""
import streamlit as st
st.set_page_config(page_title='StoreGuard | Executive Agent Governance',page_icon='🛡️',layout='wide')
nav=st.navigation([
    st.Page('cloud_executive.py',title='Executive Overview',icon=':material/dashboard:',default=True),
    st.Page('cloud_tornado.py',title='Live Tornado & DR Demo',icon=':material/thunderstorm:'),
    st.Page('cloud_execution_monitor.py', title='Execution Monitor', icon=':material/terminal:', url_path='execution-monitor'),
],position='sidebar')
nav.run()
