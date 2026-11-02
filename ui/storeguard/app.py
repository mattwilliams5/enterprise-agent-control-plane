"""StoreGuard executive application navigation."""

import streamlit as st

st.set_page_config(
    page_title="StoreGuard | Enterprise Agent Governance",
    page_icon="🛡️",
    layout="wide",
)

pages = [
    st.Page(
        "governance_overview.py",
        title="Governance Overview",
        icon=":material/dashboard:",
        default=True,
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
]

navigation = st.navigation(pages)
navigation.run()
