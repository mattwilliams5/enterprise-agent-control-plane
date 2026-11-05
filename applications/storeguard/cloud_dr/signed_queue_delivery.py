"""One-worker local HTTP signed queue delivery using Batch 3 leased claims.

No cloud service deployment, no shared API key, no credentials saved in queue.
A fresh Ed25519 nonce is generated for EVERY HTTP delivery attempt.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from applications.storeguard.cloud_dr.store_identity import sign_order_request


def deliver_signed_queue(state, *, identity_directory, base_url='http://127.0.0.1:8081',
                         max_items=100, lease_seconds=120, transport=None):
    parsed = urlsplit(base_url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.path not in ('', '/') or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError('Signed demo worker only supports localhost HTTP')
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1:
        raise ValueError('max_items must be positive')
    if lease_seconds < 30:
        raise ValueError('lease_seconds must be at least 30')
    directory = Path(identity_directory)
    results = []
    seen = set()
    with httpx.Client(base_url=base_url, timeout=10, transport=transport,
                      trust_env=False) as client:
        for _ in range(max_items):
            claim = state.claim(lease_seconds=lease_seconds)
            if claim is None:
                break
            identity = (claim.store_id, claim.order_id)
            if identity in seen:
                # Skip a second submission in the same pass, even if a test
                # clock bypasses exponential backoff.
                state.settle(claim, outcome='unknown')
                break
            seen.add(identity)
            secret = directory / f'store-{claim.store_id}.ed25519'
            if not secret.is_file():
                outcome, receipt, code = 'no_credentials', None, None
            else:
                body = json.dumps({'order_id': claim.order_id,
                                   'amount_cents': claim.amount_cents,
                                   'idempotency_key': claim.idempotency_key},
                                  separators=(',', ':')).encode()
                try:
                    key = Ed25519PrivateKey.from_private_bytes(secret.read_bytes())
                    headers = sign_order_request(key, store_id=claim.store_id,
                                                 key_id='key-v1', body=body)
                    response = client.post('/orders', content=body, headers=headers)
                    code = response.status_code
                    if code == 200:
                        data = response.json()
                        receipt = data.get('receipt_id')
                        valid = (data.get('status') in ('committed', 'duplicate')
                                 and data.get('store_id') == claim.store_id
                                 and data.get('order_id') == claim.order_id
                                 and isinstance(receipt, str) and bool(receipt))
                        outcome = 'acknowledged' if valid else 'unknown'
                    elif code in (401, 403, 409, 422):
                        outcome, receipt = 'rejected', None
                    else:
                        outcome, receipt = 'unknown', None
                except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                    outcome, receipt, code = 'unknown', None, None
            settled = state.settle(claim, outcome=outcome,
                                   receipt_id=receipt if outcome == 'acknowledged' else None,
                                   status_code=code)
            results.append({'store_id': claim.store_id, 'order_id': claim.order_id,
                            'outcome': outcome if settled else 'stale_lease',
                            'status_code': code})
    return results
