"""StoreGuard operator-side Cloud Run execution and read-only cloud evidence.

Local one-click operation requires a loopback-bound Streamlit process and an
explicit local operator flag; hosted UIs remain read-only. IAM is the true
Google Cloud authorization boundary, never a button or environment variable.
"""
from __future__ import annotations

import os
from google.auth import default
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore

PROJECT = 'storeguard-dr-demo-2026'
REGION = 'us-central1'
JOB = 'storeguard-one-trigger-demo'
DATABASE = 'storeguard-executive-evidence'
BASE = f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}'
OP_PREFIX = f'projects/{PROJECT}/locations/{REGION}/operations/'
EXPOSED = ('SG-002', 'SG-003', 'SG-004', 'SG-007', 'SG-008', 'SG-009')
SOURCE = 'storeguard_real_governed_demo_with_simulated_weather_and_outage'


def _db():
    return firestore.Client(project=PROJECT, database=DATABASE)


def get_events(*, limit=200, client=None):
    if not 1 <= limit <= 300:
        raise ValueError('Invalid event limit')
    db = client or _db()
    rows = []
    for snapshot in (db.collection('storeguard_demo_events')
                     .order_by('timestamp', direction=firestore.Query.DESCENDING)
                     .limit(limit).stream()):
        item = snapshot.to_dict() or {}
        if item.get('source') == SOURCE and isinstance(item.get('demo_run_id'), str):
            rows.append(item)
    return rows


def get_agent_decisions(*, limit=200, client=None):
    db = client or _db()
    return [snap.to_dict() or {} for snap in (
        db.collection('storeguard_agent_decisions')
        .order_by('recorded_at', direction=firestore.Query.DESCENDING)
        .limit(limit).stream())]


def _http():
    creds, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    return AuthorizedSession(creds)


def _request(method, suffix, *, body=None, session=None):
    response = (session or _http()).request(
        method, 'https://run.googleapis.com/v2/' + suffix, json=body, timeout=20)
    response.raise_for_status()
    return response.json()


def local_trigger_configured(env=None):
    env = os.environ if env is None else env
    return (env.get('STOREGUARD_GUI_LOCAL_OPERATOR') == '1'
            and env.get('STOREGUARD_GUI_BIND_ADDRESS') == '127.0.0.1')


def run_demo(*, session=None, env=None):
    """Run a single cloud job; invocation only from a deliberate UI click.

    No local process can enforce per-user access on a remotely exposed site.
    Consequently this function rejects hosted launch mode entirely.
    """
    if not local_trigger_configured(env):
        raise PermissionError('Live launch is available only in the loopback-only operator app')
    latest = get_latest_execution(session=session)
    if latest and not latest.get('completionTime') and not latest.get('failedCount'):
        raise RuntimeError('A recent Cloud Run execution is still pending; no duplicate launch')
    return _request('POST', f'projects/{PROJECT}/locations/{REGION}/jobs/{JOB}:run',
                    body={}, session=session)


def get_operation(operation_name, *, session=None):
    if not isinstance(operation_name, str) or not operation_name.startswith(OP_PREFIX):
        raise ValueError('Unexpected operation name')
    return _request('GET', operation_name, session=session)


def get_latest_execution(*, session=None):
    data = _request('GET', f'projects/{PROJECT}/locations/{REGION}/jobs/{JOB}/executions?pageSize=10',
                    session=session)
    items = data.get('executions', [])
    return max(items, key=lambda item: item.get('createTime', '')) if items else None


def grouped_runs(events):
    groups = {}
    for event in events:
        groups.setdefault(event['demo_run_id'], []).append(event)
    return sorted(groups.items(), key=lambda pair:
                  max(str(item.get('timestamp', '')) for item in pair[1]), reverse=True)


def summarize(events):
    threat = next((e.get('detail') or {} for e in events
                   if e.get('event_type') == 'THREAT_ASSESSED'), {})
    receipt = next((e.get('detail') or {} for e in events
                    if e.get('event_type') == 'DR_RECEIPT_VERIFIED'), {})
    agents = [e.get('detail') or {} for e in events if e.get('event_type') == 'AGENT_COMPLETED']
    order = receipt.get('order') or {}
    verified = bool(receipt.get('status') == 'recovery_transaction_verified'
                    and order.get('outcome') == 'acknowledged'
                    and order.get('region') == 'recovery'
                    and order.get('receipt_id'))
    return {'exposed': threat.get('exposed_store_ids', []), 'agents': agents,
            'receipt': receipt, 'verified': verified}
