"""Read-only, evidence-derived executive narrative for StoreGuard.

This module does not launch jobs, read credentials or infer cloud service health.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo('America/New_York')
SAFE_RUN = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')
LABELS = {
    'THREAT_ASSESSED': 'Weather exposure assessed',
    'AGENT_COMPLETED': 'Governed agent action completed',
    'DR_RECEIPT_VERIFIED': 'Recovery receipt verified',
}


def timestamp_pair(value):
    """Return Eastern display and UTC detail; never guess a naive timezone."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return ('Time not available', 'Timestamp cannot be parsed')
    else:
        return ('Time not available', 'Timestamp not recorded')
    if dt.tzinfo is None or dt.utcoffset() is None:
        return ('Timezone unknown', 'Naive timestamp; conversion withheld')
    return (dt.astimezone(EASTERN).strftime('%b %-d, %Y · %-I:%M:%S %p %Z'),
            dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))


def _safe_id(value):
    value = str(value or '')
    return value if re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}', value) else ''


def _safe_action(value):
    value = str(value or '')
    return value if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.:-]{0,79}', value) else ''


def event_rows(events):
    """Allowlist readable event metadata; never display arbitrary raw details."""
    output = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get('event_type')
        if event_type not in LABELS:
            continue
        detail = event.get('detail')
        detail = detail if isinstance(detail, dict) else {}
        time_local, time_utc = timestamp_pair(event.get('timestamp'))
        agent = _safe_action(detail.get('agent_id')) if event_type == 'AGENT_COMPLETED' else ''
        action = _safe_action(detail.get('action')) if event_type == 'AGENT_COMPLETED' else ''
        output.append({
            'When (Eastern)': time_local,
            'Event': LABELS[event_type],
            'Agent': agent,
            'Action': action,
            'Authorization ID': _safe_id(detail.get('authorization_run_id')) if event_type == 'AGENT_COMPLETED' else '',
            'Protected gate ID': _safe_id(detail.get('action_gate_run_id')) if event_type == 'AGENT_COMPLETED' else '',
            'Action run ID': _safe_id(detail.get('action_run_id')) if event_type == 'AGENT_COMPLETED' else '',
            'Time (UTC)': time_utc,
            '_sort': _sortkey(event.get('timestamp')),
        })
    output.sort(key=lambda item: item['_sort'])
    for item in output:
        item.pop('_sort')
    return output


def _sortkey(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return ''
    else:
        return ''
    if dt.tzinfo is None or dt.utcoffset() is None:
        return ''
    return dt.astimezone(timezone.utc).isoformat()


def action_audit_rows(summary, tools, decisions):
    """Correlate only allowlisted audit metadata for the selected demo run."""
    agents = summary.get('agents') or []
    action_ids = {_safe_id(a.get('action_run_id')) for a in agents if isinstance(a, dict)}
    governance_ids = {_safe_id(a.get(field)) for a in agents if isinstance(a, dict)
                      for field in ('authorization_run_id', 'action_gate_run_id')}
    action_ids.discard('')
    governance_ids.discard('')
    rows = []
    for kind, collection, field, allowed_ids in (
        ('Tool event', tools, 'action_run_id', action_ids),
        ('Authorization record', decisions, 'run_id', governance_ids),
    ):
        for entry in collection:
            if not isinstance(entry, dict):
                continue
            correlation_id = _safe_id(entry.get(field))
            if not correlation_id or correlation_id not in allowed_ids:
                continue
            local_time, utc_time = timestamp_pair(
                entry.get('timestamp') or entry.get('recorded_at'))
            rows.append({
                'When (Eastern)': local_time,
                'Evidence': kind,
                'Agent': _safe_action(entry.get('agent_id')),
                'Action': _safe_action(entry.get('action')),
                'Event': _safe_action(entry.get('event_type')),
                'Correlated ID': correlation_id,
                'Time (UTC)': utc_time,
                '_sort': _sortkey(entry.get('timestamp') or entry.get('recorded_at')),
            })
    rows.sort(key=lambda item: item['_sort'])
    for row in rows:
        row.pop('_sort')
    return rows


def regional_evidence(summary):
    """Evidence contract consistent with the hosted Level 1 summary."""
    receipt = summary.get('receipt') or {}
    order = receipt.get('order') or {}
    attempts = order.get('attempts') or []
    primary_simulated = any(
        isinstance(attempt, dict) and attempt.get('region') == 'primary'
        and attempt.get('error') == 'SIMULATED_CLIENT_SIDE_OUTAGE'
        for attempt in attempts)
    recovery_200 = any(
        isinstance(attempt, dict) and attempt.get('region') == 'recovery'
        and attempt.get('status_code') == 200
        for attempt in attempts)
    verified = bool(summary.get('verified') is True
                    and receipt.get('status') == 'recovery_transaction_verified'
                    and order.get('outcome') == 'acknowledged'
                    and order.get('region') == 'recovery'
                    and order.get('receipt_id')
                    and recovery_200)
    governed = [agent for agent in summary.get('agents', [])
                if isinstance(agent, dict) and all(agent.get(field)
                for field in ('agent_id', 'authorization_run_id',
                              'action_gate_run_id', 'action_run_id'))]
    return {'primary_simulated': primary_simulated, 'recovery_200': recovery_200,
            'verified': verified, 'receipt_id': order.get('receipt_id') if verified else None,
            'governed_agents': governed}


def narrative(summary, events):
    """Build only claims supported by persisted demonstration evidence."""
    region = regional_evidence(summary)
    kinds = {e.get('event_type') for e in events if isinstance(e, dict)}
    agents = region['governed_agents']
    receipt = region['verified']
    stages = [
        ('01 · Simulated threat', 'Weather impact assessed',
         'Six-store exposure is a fictional exercise, not real weather telemetry.',
         'Recorded' if 'THREAT_ASSESSED' in kinds else 'Not recorded'),
        ('02 · Vault + StoreGuard', 'Agent identity and scoped action governance',
         'The workflow uses Vault workload authentication and short-lived credentials. '
         'Recorded authorization and protected-action IDs are StoreGuard policy evidence; '
         'Vault token creation and revocation require separate Vault/runner audit verification.',
         f'{len(agents)} actions with IDs' if agents else 'No complete action IDs'),
        ('03 · Primary · us-central1', 'Primary client path interrupted (simulated)',
         'Client-side failure injection only. The primary Cloud Run service stays deployed.',
         'Simulated' if region['primary_simulated'] else 'Not recorded'),
        ('04 · Recovery · us-east4', 'Signed transaction reaches recovery',
         'A real HTTP acknowledgment is shown only when recorded in the order attempts.',
         'HTTP 200' if region['recovery_200'] else 'Not acknowledged'),
        ('05 · Operational evidence', 'Firestore order receipt checked',
         'The receipt is independently confirmed in the demonstration job, not '
         'proof of full automated regional failover.',
         'Verified' if receipt else 'Not verified'),
        ('06 · Vault lifecycle closure', 'Review token revocation and audit',
         'The runner is designed to revoke short-lived Vault credentials. '
         'This event stream does not independently prove token revocation; '
         'consult the Vault audit or Cloud Run execution evidence.',
         'External audit required'),
    ]
    return {'stages': stages, 'receipt_id': region['receipt_id'],
            'verified': receipt, 'actions': len(agents),
            'exposed': len(summary.get('exposed') or []),
            'primary_simulated': region['primary_simulated'],
            'regional_ack': region['recovery_200']}


def monitor_url(browser_url, run_id):
    """Make a same-origin link; do not trust arbitrary external redirect hosts."""
    if not isinstance(run_id, str) or not SAFE_RUN.fullmatch(run_id):
        raise ValueError('Unexpected run identifier')
    parsed = urlsplit(browser_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Unexpected app URL')
    return f'{parsed.scheme}://{parsed.netloc}/execution-monitor?run={quote(run_id, safe="")}'


def show_monitor_link(run_id):
    import streamlit as st
    try:
        url = monitor_url(st.context.url, run_id)
    except (AttributeError, ValueError):
        st.caption('Open Execution Monitor using the sidebar navigation.')
        return
    st.link_button('↗ Open Execution Monitor (new window)', url,
                   use_container_width=False)


def show_story(summary, events, *, run_id):
    import streamlit as st
    story = narrative(summary, events)
    st.subheader('The incident story · Vault-governed regional recovery')
    st.info('Security backbone: Vault authenticates agent workloads and manages credential lifetimes. StoreGuard authorizes each scoped action. Audit evidence must support every claim.')
    st.caption('Recorded exercise evidence · all displayed times are Eastern (EST/EDT)')
    if story['verified'] and story['primary_simulated']:
        st.success('Outcome: the recovery region acknowledged a signed order, and Firestore verification succeeded. The primary disruption was simulated.')
    elif story['verified']:
        st.info('Recovery receipt verified; primary interruption not independently recorded in this event set.')
    else:
        st.warning('No end-to-end verified recovery claim can be made for this run.')
    c1, c2, c3 = st.columns(3)
    c1.metric('Simulated exposed stores', story['exposed'])
    c2.metric('Governed actions with IDs', story['actions'])
    c3.metric('Recovery receipt', 'VERIFIED' if story['verified'] else 'NOT VERIFIED')
    st.markdown('**Begin: Primary · us-central1**  →  **Finish: Recovery · us-east4**')
    st.caption('Regional transfer is a real signed order sent to the recovery endpoint. This is not a real outage or automatic failover.')
    for heading, label, explanation, state in story['stages']:
        st.markdown(f'**{heading} — {label}**  ·  `{state}`')
        st.caption(explanation)
    rows = event_rows(events)
    if rows:
        st.markdown('**When it happened · Eastern Time**')
        st.dataframe([{key: item[key] for key in ('When (Eastern)', 'Event', 'Agent', 'Action')}
                      for item in rows], hide_index=True, use_container_width=True)
    st.caption(f'Exercise run: {run_id}')
    if story['receipt_id']:
        st.caption(f'Verified receipt: {story["receipt_id"]}')
    show_monitor_link(run_id)
