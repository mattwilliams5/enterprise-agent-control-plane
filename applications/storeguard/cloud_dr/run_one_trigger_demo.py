"""One-trigger StoreGuard Cloud Run Job entrypoint (explicitly armed demo only).

Never deploy as an unauthenticated HTTP endpoint. The simulated tornado and
client-side primary outage are NOT observations of real-world weather/outages.
No store state transition or human approval is performed.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from google.cloud import firestore
from openai import OpenAI

from applications.storeguard.cloud_dr.live_agent_handlers import build_live_handlers
from applications.storeguard.cloud_dr.live_agent_permissions import build_permission_checks
from applications.storeguard.cloud_dr.live_agent_runner import build_live_runner
from applications.storeguard.cloud_dr.live_signed_failover import (
    PrivateRegion, submit_signed_failover,
)
from applications.storeguard.cloud_dr.one_trigger_demo import execute_demo, INCIDENT
from applications.storeguard.store_network import build_demo_network
from applications.storeguard.threat_evaluation import WeatherThreat, evaluate_threat

PROJECT = 'storeguard-dr-demo-2026'
DATABASE = 'storeguard-executive-evidence'
# This identity is enrolled in the operational order ledger, not the simulated store ID.
TRANSACTION_STORE_ID = '1802'
PRIMARY_URL = 'https://storeguard-orders-primary-2zr27trg4a-uc.a.run.app'
RECOVERY_URL = 'https://storeguard-orders-recovery-2zr27trg4a-uk.a.run.app'


def read_enrolled_store_key():
    """Read existing enrolled demo key from a mounted secret, never log it."""
    key_path = os.environ.get('STOREGUARD_STORE_KEY_FILE')
    if not key_path or not Path(key_path).is_file():
        raise RuntimeError('Existing enrolled store signing key must be mounted as secret file')
    if not os.environ.get('STOREGUARD_STORE_KEY_ID'):
        raise RuntimeError('Enrolled STOREGUARD_STORE_KEY_ID required')
    raw = Path(key_path).read_bytes().strip()
    try:
        decoded = base64.b64decode(raw, validate=True)
        return Ed25519PrivateKey.from_private_bytes(decoded)
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Mounted store key must be base64-encoded raw 32-byte Ed25519 key') from exc


def verify_ledger_receipt(*, project, store_id, order_id, idempotency_key, receipt_id):
    """Independently read the DEFAULT operational ledger, do not write to it."""
    from applications.storeguard.cloud_dr.order_ledger import FirestoreOrderLedger
    expected_receipt_id = FirestoreOrderLedger._digest(store_id, idempotency_key)
    if receipt_id != expected_receipt_id:
        raise RuntimeError('Unexpected receipt ID')
    ledger = firestore.Client(project=project, database='(default)')
    snap = ledger.collection('storeguard_orders').document(expected_receipt_id).get()
    if not snap.exists:
        raise RuntimeError('Receipt not persisted in shared Firestore ledger')
    data = snap.to_dict() or {}
    if (data.get('store_id') != store_id or data.get('order_id') != order_id
        or data.get('idempotency_key') != idempotency_key):
        raise RuntimeError('Persisted receipt does not match signed order')
    return True


def main():
    if not os.getenv('CLOUD_RUN_JOB'):
        raise RuntimeError('Cloud Run Job runtime required')
    if os.getenv('STOREGUARD_DEMO_ARMED') != 'SIMULATED_PRIMARY_OUTAGE_REAL_ORDER':
        raise RuntimeError('Explicit demo arming acknowledgement required')
    if os.getenv('GOOGLE_CLOUD_PROJECT') != PROJECT:
        raise RuntimeError('Unexpected GCP project')

    key = read_enrolled_store_key()
    key_id = os.environ['STOREGUARD_STORE_KEY_ID']
    db = firestore.Client(project=PROJECT, database=DATABASE)
    network = build_demo_network()
    assessment = evaluate_threat(network, WeatherThreat(INCIDENT, 35.4676, -97.5164, 15))
    handlers = build_live_handlers(network=network, assessment=assessment,
                                   client=OpenAI(), model='gpt-4.1-mini')
    delegation_check, scope_check = build_permission_checks(client=db)
    runner = build_live_runner(handlers=handlers,
                               delegation_check=delegation_check,
                               scope_check=scope_check)

    def persist(demo_id, event_type, detail):
        record = {'demo_run_id': demo_id, 'event_type': event_type,
                  'timestamp': datetime.now(timezone.utc).isoformat(),
                  'source': 'storeguard_real_governed_demo_with_simulated_weather_and_outage',
                  'detail': detail}
        # Durable, create-only evidence, including partial progress when interrupted.
        db.collection('storeguard_demo_events').document(uuid4().hex).create(record)

    def submit(demo_id):
        order_id = f'demo-{demo_id}'
        idempotency_key = f'demo-{demo_id}'
        result = submit_signed_failover(
            primary=PrivateRegion('primary', PRIMARY_URL),
            recovery=PrivateRegion('recovery', RECOVERY_URL),
            store_id=TRANSACTION_STORE_ID, key_id=key_id, private_key=key,
            order_id=order_id, amount_cents=125,
            idempotency_key=idempotency_key,
            simulate_primary_outage=True,
        )
        if result.get('outcome') == 'acknowledged' and result.get('region') == 'recovery':
            verify_ledger_receipt(project=PROJECT, store_id=TRANSACTION_STORE_ID,
                                  order_id=order_id, idempotency_key=idempotency_key,
                                  receipt_id=result['receipt_id'])
        return result

    result = execute_demo(governed_runner=runner,
                          evidence_factory=lambda intent: intent.agent_id,
                          submit_order=submit,
                          persist_event=persist,
                          transaction_store_id=TRANSACTION_STORE_ID)
    print('PASS: One-trigger StoreGuard demo completed')
    print('PASS: Fresh Vault governed weather and SRE actions')
    print('PASS: Recovery service acknowledged actual signed order')
    print('PASS: Shared Firestore receipt independently verified')
    print('Simulated: tornado exposure and primary client outage; no real cloud outage')
    print('Store state recovery: NOT APPROVED OR PERFORMED')
    print('Demo run ID:', result['demo_run_id'])
    print('Receipt ID:', result['order']['receipt_id'])


if __name__ == '__main__':
    main()
