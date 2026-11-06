"""Delivery worker using leased SQLite claims + existing router.submit API.

Use ONE worker per SQLite database until lease heartbeats/long-call fencing
have been operationally validated. No credentials are stored in SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReliableEvent:
    store_id: str
    order_id: str
    outcome: str
    region: str | None = None
    status_code: int | None = None


def deliver_reliably(state, router, credentials, *, max_items=100, lease_seconds=120):
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
        raise ValueError('max_items must be a positive integer')
    events = []
    # Prevent immediate replay of the same row within one batch, even with
    # a zero-latency test clock or operationally shortened backoff.
    seen = set()
    for _ in range(max_items):
        claim = state.claim(lease_seconds=lease_seconds)
        if claim is None:
            break
        identity = (claim.store_id, claim.order_id)
        if identity in seen:
            # This should not occur with normal positive backoff.
            state.settle(claim, outcome='unknown')
            break
        seen.add(identity)
        key = credentials.get(claim.store_id)
        result = None
        if not key:
            outcome = 'no_credentials'
        else:
            payload = {'order_id': claim.order_id, 'amount_cents': claim.amount_cents,
                       'idempotency_key': claim.idempotency_key}
            headers = {'X-Store-ID': claim.store_id, 'X-API-Key': key}
            try:
                result = router.submit(payload, headers)
            except Exception:
                # Includes lost ACK: transaction may have committed.
                result = None
            response_outcome = result.get('outcome') if isinstance(result, dict) else None
            receipt = result.get('receipt_id') if isinstance(result, dict) else None
            if response_outcome == 'acknowledged' and isinstance(receipt, str) and receipt:
                outcome = 'acknowledged'
            elif response_outcome == 'rejected':
                outcome = 'rejected'
            else:
                outcome = 'unknown'
        region = result.get('region') if isinstance(result, dict) else None
        status_code = result.get('status_code') if isinstance(result, dict) else None
        completed = state.settle(claim, outcome=outcome,
                                 receipt_id=receipt if outcome == 'acknowledged' else None,
                                 status_code=status_code)
        events.append(ReliableEvent(claim.store_id, claim.order_id,
                                    outcome if completed else 'stale_lease', region, status_code))
    return events
