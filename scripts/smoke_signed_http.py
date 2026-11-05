"""40-store real HTTP signed request smoke test (offline by default).

An explicit --ack-live-writes flag is required for --mode firestore. The
service must be started separately and bound to 127.0.0.1. This script does
not start services, create cloud resources, or output private keys.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from applications.storeguard.cloud_dr.store_identity import sign_order_request


def run_fleet(directory: Path, *, count: int, start: int, base_url: str,
              verify_replay: bool = True, mode: str = "offline") -> dict:
    path = directory / 'trusted_stores.sqlite3'
    if not path.is_file():
        raise FileNotFoundError(f'Missing enrolled registry: {path}')
    if not (1 <= count <= 1000 and 1 <= start <= 999999):
        raise ValueError('Invalid fleet dimensions')
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Only local HTTP server endpoints are allowed')
    run_id = uuid.uuid4().hex[:12]
    stats = {'stores': 0, 'commits': 0, 'replays_rejected': 0,
             'idempotent_retries': 0, 'run_id': run_id}
    with httpx.Client(base_url=base_url, timeout=12, trust_env=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        if health.json().get('authentication') != 'signed-only-local':
            raise RuntimeError('Target is not the StoreGuard signed-only API')
        marker = client.get('/demo-backend')
        if mode == 'offline' and (marker.status_code != 200 or marker.json().get('backend') != 'offline-sqlite-demo'):
            raise RuntimeError('Expected explicit offline SQLite demo server')
        if mode == 'firestore' and marker.status_code != 404:
            raise RuntimeError('Refusing to treat offline/demo server as live Firestore')
        for number in range(start, start + count):
            sid = str(number)
            private_file = directory / f'store-{sid}.ed25519'
            key = Ed25519PrivateKey.from_private_bytes(private_file.read_bytes())
            body = json.dumps({'order_id': f'HTTP{run_id}{sid}', 'amount_cents': 2599,
                               'idempotency_key': f'HTTPKEY{run_id}{sid}'}, separators=(',', ':')).encode()
            headers = sign_order_request(key, store_id=sid, key_id='key-v1', body=body)
            response = client.post('/orders', content=body, headers=headers)
            if response.status_code != 200 or response.json().get('status') != 'committed' or response.json().get('store_id') != sid:
                raise AssertionError(f'{sid}: first HTTP submission failed: {response.status_code}: {response.text[:160]}')
            receipt = response.json()['receipt_id']
            stats['commits'] += 1
            if verify_replay:
                replay = client.post('/orders', content=body, headers=headers)
                if replay.status_code != 401:
                    raise AssertionError(f'{sid}: replay not denied: {replay.status_code}')
                stats['replays_rejected'] += 1
            new_headers = sign_order_request(key, store_id=sid, key_id='key-v1', body=body)
            retry = client.post('/orders', content=body, headers=new_headers)
            if retry.status_code != 200 or retry.json().get('status') != 'duplicate' or retry.json().get('receipt_id') != receipt:
                raise AssertionError(f'{sid}: retry mismatch: {retry.status_code}: {retry.text[:160]}')
            stats['idempotent_retries'] += 1
            stats['stores'] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='.local/storeguard-identity-demo')
    parser.add_argument('--count', type=int, default=40)
    parser.add_argument('--start', type=int, default=1800)
    parser.add_argument('--base-url', default='http://127.0.0.1:8081')
    parser.add_argument('--mode', choices=('offline', 'firestore'), default='offline')
    parser.add_argument('--ack-live-writes', action='store_true')
    args = parser.parse_args()
    if args.mode == 'firestore' and not args.ack_live_writes:
        parser.error('Live Firestore mode requires --ack-live-writes')
    if args.mode == 'offline' and args.ack_live_writes:
        parser.error('Do not provide live-write acknowledgment in offline mode')
    stats = run_fleet(Path(args.directory), count=args.count, start=args.start,
                      base_url=args.base_url, mode=args.mode)
    print('PASS real signed HTTP fleet:', json.dumps(stats, sort_keys=True))
    print('Mode:', args.mode, '(server mode must be verified independently)')


if __name__ == '__main__':
    main()
