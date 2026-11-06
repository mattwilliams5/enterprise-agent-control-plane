"""Controlled StoreGuard cloud application-route failover acceptance demo.

Run from repository root. Requires existing, enrolled demo identities and two
running authenticated gcloud Cloud Run proxies. Never uploads private keys.
A simulated primary route failure is an application routing fault injection;
it is NOT a Google Cloud regional outage or an automated health detector.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from applications.storeguard.cloud_dr.store_identity import sign_order_request


def now():
    return datetime.now(timezone.utc).isoformat()


def create_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS demo_orders (
            run_id TEXT NOT NULL, store_id TEXT NOT NULL,
            order_id TEXT NOT NULL, body BLOB NOT NULL,
            state TEXT NOT NULL, route TEXT, receipt_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, store_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS demo_events (
            event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
            created_at TEXT NOT NULL, store_id TEXT,
            event_type TEXT NOT NULL, details TEXT NOT NULL)''')
        db.commit()


def event(db, run_id, event_type, store_id=None, details=''):
    db.execute('INSERT INTO demo_events VALUES (?,?,?,?,?,?)',
               (uuid4().hex, run_id, now(), store_id, event_type, details))
    db.commit()


def ensure_healthy(client, url, label):
    response = client.get(f'{url}/health')
    response.raise_for_status()
    body = response.json()
    if body.get('authentication') != 'shared-signed-only' or body.get('backend') != 'firestore':
        raise RuntimeError(f'{label} is not the expected cloud signed-only API')
    print(f'PASS: {label} health (shared-signed-only, firestore)')


def assert_local_url(url):
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1') or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Only localhost HTTP Cloud Run proxy URLs are accepted')


def send(client, endpoint, body, store_id, key):
    headers = sign_order_request(key, store_id=store_id, key_id='key-v1', body=body)
    response = client.post(endpoint + '/orders', content=body, headers=headers)
    return response, headers


def require_status(response, status, outcome=None):
    if response.status_code != status:
        raise AssertionError(f'Unexpected HTTP {response.status_code}; expected {status}; body={response.text[:200]}')
    result = response.json()
    if outcome and result.get('status') != outcome:
        raise AssertionError(f'Unexpected response status {result.get("status")}; expected {outcome}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary', default='http://127.0.0.1:8080')
    parser.add_argument('--recovery', default='http://127.0.0.1:9092')
    parser.add_argument('--identity-dir', default='.local/storeguard-identity-demo')
    parser.add_argument('--state-dir', default='.local/cloud-demo')
    parser.add_argument('--ack-live-writes', action='store_true')
    args = parser.parse_args()
    if not args.ack_live_writes:
        parser.error('Real Firestore writes require --ack-live-writes')
    assert_local_url(args.primary)
    assert_local_url(args.recovery)
    identity = Path(args.identity_dir)
    if not (identity / 'trusted_stores.sqlite3').is_file():
        parser.error('Local store identity registry missing; enroll first')
    for sid in map(str, range(1800, 1840)):
        path = identity / f'store-{sid}.ed25519'
        if not path.is_file():
            parser.error(f'Missing private key for store {sid}')
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    db_path = state / 'route-failover.sqlite3'
    create_db(db_path)
    run_id = uuid4().hex[:12]
    counters = dict(primary_commits=0, queued_during_outage=0,
                    recovered_commits=0, cross_region_duplicates=0,
                    replays_rejected=0, pending=0)
    print(f'RUN: {run_id}')
    print('MODE: CONTROLLED APPLICATION-ROUTE FAILURE (not a Google Cloud region outage)')
    print('Preserving prior Firestore orders and local audit runs')
    with httpx.Client(timeout=30, trust_env=False) as client, closing(sqlite3.connect(db_path, timeout=30)) as db:
        ensure_healthy(client, args.primary, 'primary')
        ensure_healthy(client, args.recovery, 'recovery')
        keys = {}
        for number in range(1800, 1840):
            sid = str(number)
            keys[sid] = Ed25519PrivateKey.from_private_bytes(
                (identity / f'store-{sid}.ed25519').read_bytes())
            body = json.dumps({'order_id': f'FAIL{run_id}{sid}', 'amount_cents': 2599,
                               'idempotency_key': f'FAILKEY{run_id}{sid}'}, separators=(',', ':')).encode()
            db.execute('INSERT INTO demo_orders (run_id,store_id,order_id,body,state) VALUES (?,?,?,?,?)',
                       (run_id, sid, f'FAIL{run_id}{sid}', body, 'PENDING'))
        db.commit()
        event(db, run_id, 'RUN_CREATED', details='40 unique signed order intents durably stored')

        # First half succeeds in primary during normal operations.
        for number in range(1800, 1820):
            sid = str(number)
            body = db.execute('SELECT body FROM demo_orders WHERE run_id=? AND store_id=?',
                              (run_id, sid)).fetchone()[0]
            response, _ = send(client, args.primary, body, sid, keys[sid])
            result = require_status(response, 200, 'committed')
            receipt = result['receipt_id']
            db.execute('UPDATE demo_orders SET state=?,route=?,receipt_id=?,attempts=attempts+1 WHERE run_id=? AND store_id=?',
                       ('ACKNOWLEDGED', 'primary', receipt, run_id, sid))
            db.commit()
            event(db, run_id, 'ACKNOWLEDGED_PRIMARY', sid, receipt)
            counters['primary_commits'] += 1
        print('PHASE 1: 20/20 normal primary orders acknowledged')

        # Explicit fault injection in our routing decision; the real primary stays healthy.
        event(db, run_id, 'PRIMARY_ROUTE_UNAVAILABLE_SIMULATED',
              details='Application router fault injection; Cloud Run service not stopped')
        queued = db.execute('SELECT COUNT(*) FROM demo_orders WHERE run_id=? AND state=?',
                            (run_id, 'PENDING')).fetchone()[0]
        assert queued == 20
        counters['queued_during_outage'] = queued
        print(f'PHASE 2: SIMULATED primary route fault, {queued} orders durably PENDING')

        # Automatic recovery route selection for each pending durable queue item.
        rows = db.execute('SELECT store_id,body FROM demo_orders WHERE run_id=? AND state=? ORDER BY store_id',
                          (run_id, 'PENDING')).fetchall()
        for sid, body in rows:
            response, _ = send(client, args.recovery, body, sid, keys[sid])
            result = require_status(response, 200, 'committed')
            receipt = result['receipt_id']
            db.execute('UPDATE demo_orders SET state=?,route=?,receipt_id=?,attempts=attempts+1 WHERE run_id=? AND store_id=?',
                       ('ACKNOWLEDGED', 'recovery', receipt, run_id, sid))
            db.commit()
            event(db, run_id, 'ACKNOWLEDGED_RECOVERY', sid, receipt)
            counters['recovered_commits'] += 1
        print('PHASE 3: 20/20 queued orders acknowledged through recovery')

        # In both directions, prove common ledger and common nonce state.
        rows = db.execute('SELECT store_id,body,route,receipt_id FROM demo_orders WHERE run_id=? ORDER BY store_id',
                          (run_id,)).fetchall()
        for sid, body, route, receipt in rows:
            opposite = args.recovery if route == 'primary' else args.primary
            fresh_response, fresh_headers = send(client, opposite, body, sid, keys[sid])
            same = require_status(fresh_response, 200, 'duplicate')
            if same['receipt_id'] != receipt:
                raise AssertionError(f'{sid}: receipt mismatch')
            counters['cross_region_duplicates'] += 1
            # Replay the just-accepted signed request against the first region.
            origin = args.primary if route == 'primary' else args.recovery
            replay_response = client.post(origin + '/orders', content=body, headers=fresh_headers)
            require_status(replay_response, 401)
            counters['replays_rejected'] += 1
            event(db, run_id, 'INTEGRITY_VERIFIED', sid, 'opposite-region duplicate + cross-region nonce rejection')
        counters['pending'] = db.execute('SELECT COUNT(*) FROM demo_orders WHERE run_id=? AND state!=?',
                                         (run_id, 'ACKNOWLEDGED')).fetchone()[0]
        assert counters == dict(primary_commits=20, queued_during_outage=20,
                                recovered_commits=20, cross_region_duplicates=40,
                                replays_rejected=40, pending=0)
        event(db, run_id, 'DEMO_PASSED', details=json.dumps(counters, sort_keys=True))
    summary = {'run_id': run_id, 'mode': 'simulated_primary_route_failure', **counters,
               'audit_db': str(db_path), 'completed_at': now()}
    filename = state / f'failover-summary-{run_id}.json'
    filename.write_text(json.dumps(summary, indent=2) + '\n')
    print('PHASE 4: 40/40 cross-region duplicates confirmed; 40/40 replays rejected')
    print('RESULT:', json.dumps(summary, indent=2))
    print('PASS: CONTROLLED ROUTE FAILOVER DEMO')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        print('Existing queue and event records are preserved for investigation. Do not replay identical signed nonces.', file=sys.stderr)
        sys.exit(1)
