"""Read-only presentation of StoreGuard identity and local audit evidence.

SQLite is development-only and is not a tamper-resistant audit store.
"""
import os
import sqlite3
from pathlib import Path

import streamlit as st

from applications.storeguard.investigation_controller import AGENT_NAME

AUDIT_DB = Path(os.getenv('STOREGUARD_AUDIT_DB', 'data/storeguard_security_audit.sqlite3'))


def audit_events(agent_id=None, limit=150):
    if not AUDIT_DB.is_file():
        return []
    try:
        with sqlite3.connect(f'file:{AUDIT_DB.resolve()}?mode=ro', uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_events'"
            ).fetchone()
            if not exists:
                return []
            cols = {row[1] for row in db.execute('PRAGMA table_info(execution_events)')}
            required = {'timestamp', 'agent', 'run_id', 'incident_id', 'store_id', 'event_type', 'vault_entity_id'}
            if not required.issubset(cols):
                return []
            fingerprint = 'registration_fingerprint' if 'registration_fingerprint' in cols else 'NULL AS registration_fingerprint'
            query = (
                'SELECT timestamp, agent, run_id, incident_id, store_id, event_type, '
                f'vault_entity_id, {fingerprint} FROM execution_events'
            )
            params = []
            if agent_id is not None:
                query += ' WHERE agent = ?'
                params.append(agent_id)
            query += ' ORDER BY timestamp DESC, rowid DESC LIMIT ?'
            params.append(int(limit))
            return [dict(row) for row in db.execute(query, params)]
    except (sqlite3.Error, OSError):
        return []


def latest_run(events):
    if not events:
        return None, []
    run_id = events[0]['run_id']
    return run_id, [event for event in events if event['run_id'] == run_id]


def render_identity_sidebar():
    events = audit_events(AGENT_NAME)
    run_id, run_events = latest_run(events)
    with st.sidebar:
        st.divider()
        st.subheader('Agent identity')
        st.code(AGENT_NAME, language=None)
        st.caption('Registered agent identifier · not a live authentication assertion')
        if run_id:
            st.caption('Latest recorded investigation')
            st.code(run_id, language=None)
            entity = next((e['vault_entity_id'] for e in run_events if e['vault_entity_id']), None)
            st.write('**Vault entity (recorded):**')
            st.code(entity or 'Not recorded', language=None)
            st.write('**Last recorded event:** ' + run_events[0]['event_type'])
            st.caption('Historical audit evidence; not an active Vault session')
        else:
            st.caption('No local investigation audit events yet')
        st.caption('Development SQLite audit · not tamper-resistant')
