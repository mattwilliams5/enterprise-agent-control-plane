"""Read-only Cloud Run health and approved StoreGuard demo evidence.

This module never writes Firestore, issues Vault credentials or invokes order APIs.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.cloud import firestore
import requests

RUNS_COLLECTION = 'storeguard_executive_demo_runs'


def _cloud_run_url(env_name: str) -> str:
    url = os.environ.get(env_name, '').rstrip('/')
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or not parsed.hostname or
            not parsed.hostname.endswith('.run.app') or parsed.path or
            parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError(f'{env_name} must be a Cloud Run HTTPS service URL')
    return url


def cloud_health(env_name: str) -> dict:
    """GET /health using Google-signed service identity, not browser credentials.

    /health reports application startup, not a successful ledger write.
    """
    try:
        url = _cloud_run_url(env_name)
    except ValueError:
        return {
            'healthy': False,
            'detail': 'Cloud Run URL missing or invalid'
        }
    try:
        token = id_token.fetch_id_token(Request(), url)
        response = requests.get(url + '/health', headers={'Authorization': 'Bearer ' + token}, timeout=6)
        response.raise_for_status()
        data = response.json()
        valid = (data.get('status') == 'ok' and data.get('authentication') == 'shared-signed-only'
                 and data.get('backend') == 'firestore')
        return {'healthy': bool(valid), 'detail': 'API health verified' if valid else 'Unexpected health response'}
    except Exception:
        return {'healthy': False, 'detail': 'Service unavailable or authorization failed'}


def latest_runs(client=None, limit: int = 5) -> list[dict]:
    """Only show operator-published, verified run summaries (not inferred metrics)."""
    if not 1 <= limit <= 20:
        raise ValueError('Invalid limit')
    if client is None:
        project = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCP_PROJECT')
        if not project:
            raise RuntimeError('GOOGLE_CLOUD_PROJECT must be configured')
        client = firestore.Client(project=project, database=os.environ["STOREGUARD_EVIDENCE_DATABASE"])
    results = []
    for doc in client.collection(RUNS_COLLECTION).order_by('completed_at', direction=firestore.Query.DESCENDING).limit(limit).stream():
        item = doc.to_dict() or {}
        if (item.get('source') != 'verified_local_sqlite_failover' or
            item.get('mode') != 'simulated_primary_route_failure' or
            not isinstance(item.get('run_id'), str)):
            continue
        results.append({
            'run_id': item['run_id'],
            'completed_at': str(item.get('completed_at', '')),
            'primary_commits': int(item.get('primary_commits', 0)),
            'queued_during_outage': int(item.get('queued_during_outage', 0)),
            'recovered_commits': int(item.get('recovered_commits', 0)),
            'cross_region_duplicates': int(item.get('cross_region_duplicates', 0)),
            'replays_rejected': int(item.get('replays_rejected', 0)),
            'pending': int(item.get('pending', 0)),
            'mode': item['mode'],
        })
    return results
