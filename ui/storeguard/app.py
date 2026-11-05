"""StoreGuard executive application navigation."""

import streamlit as st

st.set_page_config(
    page_title="StoreGuard | Enterprise Agent Governance",
    page_icon="🛡️",
    layout="wide",
)

# Cloud mode is deliberately limited to a read-only vetted page.
# Do not import local Vault provisioner or privileged action modules in Cloud Run.
import os
if os.environ.get("STOREGUARD_CLOUD_MODE") == "1":
    navigation = st.navigation([
        st.Page(
            "cloud_overview.py",
            title="Executive Overview",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "cloud_tornado.py",
            title="Tornado & DR Exercise",
            icon=":material/thunderstorm:",
        ),
    ], position="sidebar")
    navigation.run()
    st.stop()

pages = [
    st.Page(
        "live_mission_control.py",
        title="Live Mission Control",
        icon=":material/monitor_heart:",
        default=True,
    ),
    st.Page(
        "governance_overview.py",
        title="Governance Overview",
        icon=":material/dashboard:",
    ),
    st.Page(
        "agent_identity_activity.py",
        title="Agent Identity & Activity",
        icon=":material/fingerprint:",
    ),
    st.Page(
        "dashboard.py",
        title="Store Operations",
        icon=":material/storefront:",
    ),

    st.Page(
        "governed_analyst.py",
        title="AI Recovery Analyst",
        icon=":material/psychology:",
    ),
]

from ui.storeguard.identity_display import render_identity_sidebar

navigation = st.navigation(pages)
render_identity_sidebar()
navigation.run()
