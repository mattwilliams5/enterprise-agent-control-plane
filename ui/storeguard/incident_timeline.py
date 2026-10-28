"""Read-only Streamlit timeline for StoreGuard presentation/control-plane events.

Accepts AgentEventView-compatible objects; does not make authorization decisions.
"""
from html import escape
import streamlit as st

STATUS_LABELS = {
    "complete": ("✓", "Completed", "#2e9b74"),
    "working": ("◉", "In progress", "#4a90d9"),
    "denied": ("⛔", "Denied", "#d76565"),
    "pending": ("◷", "Awaiting approval", "#c58b34"),
    "error": ("!", "Failed", "#d76565"),
}


def render_incident_timeline(events, *, title="Incident timeline"):
    """Render events in their supplied order; works with current demo event models."""
    st.subheader(title)
    st.caption("Event history · simulated inputs and locally validated state transitions; external audit integration pending")
    if not events:
        st.info("No incident events yet. Load the tornado fixture to view the timeline.")
        return

    for index, event in enumerate(events, start=1):
        status = str(getattr(event, "status", "complete")).lower()
        symbol, label, color = STATUS_LABELS.get(status, ("•", status.title(), "#8c96a0"))
        message = escape(str(getattr(event, "message", "")))
        event_type = escape(str(getattr(event, "event_type", "UNKNOWN")))
        timestamp = escape(str(getattr(event, "timestamp", "")))
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:7px 12px;margin:6px 0;'
            'border-radius:4px;background:rgba(128,128,128,.055)">'
            f'<div style="font-weight:650">{index:02d} &nbsp; {symbol} &nbsp; {message}</div>'
            f'<div style="font-size:.78rem;opacity:.78">{timestamp} · {event_type} · '
            f'<span style="color:{color}">{escape(label)}</span></div></div>',
            unsafe_allow_html=True,
        )
