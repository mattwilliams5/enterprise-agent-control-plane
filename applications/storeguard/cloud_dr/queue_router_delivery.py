"""Additive, single-worker durable queue-to-regional-router integration.

No schema migration. Each pending row is attempted at most once per invocation.
Do not run multiple delivery workers against the same SQLite queue.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryEvent:
    store_id: str
    order_id: str
    outcome: str
    region: str | None = None
    status_code: int | None = None


def deliver_pending_via_router(queue, router, credentials, *, max_items=100):
    """Submit queued orders with their original immutable idempotency keys.

    The router's validated acknowledgement is the ONLY success condition.
    All non-acknowledged orders remain persisted and pending, including 4xx.
    Caller must investigate rejected orders instead of blindly rerunning them.

    `credentials` is a mapping of store_id -> development API key ONLY for
    local/mock tests. Do not use this authentication approach for cloud deploy.
    """
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1:
        raise ValueError('max_items must be a positive integer')

    events = []
    # Snapshot prevents immediate retry loops on the same pending order.
    for order in queue.pending()[:max_items]:
        store_id = order['store_id']
        order_id = order['order_id']
        if store_id not in credentials or not credentials[store_id]:
            events.append(DeliveryEvent(store_id, order_id, 'no_credentials'))
            continue

        payload = {
            'order_id': order_id,
            'amount_cents': order['amount_cents'],
            'idempotency_key': order['idempotency_key'],
        }
        headers = {'X-Store-ID': store_id, 'X-API-Key': credentials[store_id]}
        try:
            result = router.submit(payload, headers)
        except Exception:
            # A submission may commit before the client observes a failure.
            # Preserve the order and its idempotency identity for replay.
            events.append(DeliveryEvent(store_id, order_id, 'unknown'))
            continue

        outcome = result.get('outcome') if isinstance(result, dict) else None
        region = result.get('region') if isinstance(result, dict) else None
        status_code = result.get('status_code') if isinstance(result, dict) else None
        if outcome == 'acknowledged' and isinstance(result.get('receipt_id'), str) and result['receipt_id']:
            # Only acknowledge a confirmed router result with a receipt.
            queue.acknowledge(store_id, order_id, result['receipt_id'])
            events.append(DeliveryEvent(store_id, order_id, 'acknowledged', region))
        elif outcome == 'rejected':
            events.append(DeliveryEvent(store_id, order_id, 'rejected', region, status_code))
        else:
            events.append(DeliveryEvent(store_id, order_id, 'unknown', region, status_code))
    return events
