"""Offline HTTP smoke test of 40 enrolled store identities using a fake ledger.

No socket, cloud client, or Google Cloud writes are used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from applications.storeguard.cloud_dr.signed_order_api import (
    app, get_ledger_factory, get_registry_path,
)
from applications.storeguard.cloud_dr.store_identity import sign_order_request


class OfflineLedger:
    def __init__(self):
        self.committed = {}

    def submit(self, order):
        identity = (order.store_id, order.order_id)
        if identity in self.committed:
            receipt = self.committed[identity]
            return {'status': 'duplicate', 'store_id': order.store_id,
                    'order_id': order.order_id, 'receipt_id': receipt}
        receipt = f'OFFLINE-{order.store_id}-{order.order_id}'
        self.committed[identity] = receipt
        return {'status': 'committed', 'store_id': order.store_id,
                'order_id': order.order_id, 'receipt_id': receipt}


def run_smoke(directory: Path, store_ids: list[str]) -> dict:
    path = directory / 'trusted_stores.sqlite3'
    if not path.is_file():
        raise FileNotFoundError(f'Identity registry missing: {path}')
    ledger = OfflineLedger()
    app.dependency_overrides[get_registry_path] = lambda: path
    app.dependency_overrides[get_ledger_factory] = lambda: (lambda: ledger)
    try:
        with TestClient(app) as client:
            for store_id in store_ids:
                secret_path = directory / f'store-{store_id}.ed25519'
                key = Ed25519PrivateKey.from_private_bytes(secret_path.read_bytes())
                body = json.dumps({'order_id': f'DEMO-{store_id}', 'amount_cents': 2599,
                                   'idempotency_key': f'KEY-{store_id}'}, separators=(',', ':')).encode()
                headers = sign_order_request(key, store_id=store_id, key_id='key-v1', body=body)
                first = client.post('/orders', content=body, headers=headers)
                assert first.status_code == 200, (store_id, first.status_code, first.text)
                assert first.json()['store_id'] == store_id
                assert first.json()['status'] == 'committed'
                replay = client.post('/orders', content=body, headers=headers)
                assert replay.status_code == 401, (store_id, 'replay', replay.status_code)
                retry = client.post('/orders', content=body,
                                    headers=sign_order_request(key, store_id=store_id,
                                                               key_id='key-v1', body=body))
                assert retry.status_code == 200 and retry.json()['status'] == 'duplicate'
                assert retry.json()['receipt_id'] == first.json()['receipt_id']
        assert len(ledger.committed) == len(store_ids)
        return {'stores': len(store_ids), 'commits': len(ledger.committed),
                'replays_rejected': len(store_ids), 'idempotent_retries': len(store_ids)}
    finally:
        app.dependency_overrides.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='.local/storeguard-identity-demo')
    parser.add_argument('--count', type=int, default=40)
    parser.add_argument('--start', type=int, default=1800)
    args = parser.parse_args()
    result = run_smoke(Path(args.directory), [str(i) for i in range(args.start, args.start + args.count)])
    print('PASS offline signed HTTP fleet:', json.dumps(result, sort_keys=True))
    print('NO Firestore writes performed')


if __name__ == '__main__':
    main()
