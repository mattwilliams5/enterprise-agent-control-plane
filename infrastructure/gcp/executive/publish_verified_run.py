"""Operator-only opt-in publisher of verified local failover evidence.

Only public test counts and run ID go to Firestore. No private keys, full
transaction payloads, Vault identity data, or secrets are sent.
"""
from __future__ import annotations
import os

import argparse
import json
import sqlite3
from pathlib import Path
from google.cloud import firestore

COLLECTION = 'storeguard_executive_demo_runs'


def verify_summary(summary, db_path):
    expected = dict(primary_commits=20, queued_during_outage=20,
                    recovered_commits=20, cross_region_duplicates=40,
                    replays_rejected=40, pending=0)
    for key, expected_value in expected.items():
        if type(summary.get(key)) is not int or summary[key] != expected_value:
            raise ValueError(f'Unexpected {key}')
    run_id = summary.get('run_id')
    if not isinstance(run_id, str) or len(run_id) != 12 or not all(c in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid run ID')
    if summary.get('mode') != 'simulated_primary_route_failure':
        raise ValueError('Not a simulated route-failover run')
    uri = f'file:{db_path.resolve()}?mode=ro'
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute('''SELECT route,state,COUNT(*) FROM demo_orders
                                WHERE run_id=? GROUP BY route,state''', (run_id,)).fetchall()
        assert set(rows) == {('primary','ACKNOWLEDGED',20),('recovery','ACKNOWLEDGED',20)}, rows
        kinds = dict(conn.execute('''SELECT event_type,COUNT(*) FROM demo_events
                                    WHERE run_id=? GROUP BY event_type''', (run_id,)).fetchall())
        for key, count in {'ACKNOWLEDGED_PRIMARY':20, 'ACKNOWLEDGED_RECOVERY':20,
                           'INTEGRITY_VERIFIED':40,'DEMO_PASSED':1,
                           'PRIMARY_ROUTE_UNAVAILABLE_SIMULATED':1}.items():
            assert kinds.get(key) == count, (key, kinds.get(key))
    return {**expected, 'run_id':run_id, 'mode':summary['mode'],
            'completed_at': summary['completed_at'], 'source':'verified_local_sqlite_failover'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--state-dir', default='.local/cloud-demo')
    parser.add_argument('--project', default='storeguard-dr-demo-2026')
    parser.add_argument('--ack-publish', action='store_true')
    args = parser.parse_args()
    if not args.ack_publish: parser.error('Explicit --ack-publish required for Firestore write')
    directory = Path(args.state_dir)
    path = directory / f'failover-summary-{args.run_id}.json'
    summary = json.loads(path.read_text())
    if summary.get('run_id') != args.run_id: raise ValueError('Run ID mismatch')
    data = verify_summary(summary, directory / 'route-failover.sqlite3')
    client = firestore.Client(project=args.project, database=os.environ["STOREGUARD_EVIDENCE_DATABASE"])
    client.collection(COLLECTION).document(args.run_id).create(data)
    print('PASS: Published verified run:', args.run_id)
    print('No secrets or per-store private data uploaded.')

if __name__ == '__main__': main()
