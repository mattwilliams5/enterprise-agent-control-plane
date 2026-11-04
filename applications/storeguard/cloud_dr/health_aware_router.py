"""Routing with durable recovery preference and opt-in controlled failback.

When in recovery mode, sends ONLY to recovery. Does not probe automatically.
Uses the existing router for normal primary-first submission semantics.
"""
from __future__ import annotations

import httpx


class HealthAwareRouter:
    def __init__(self, router, health):
        self.router = router
        self.health = health

    def submit(self, payload, headers):
        if self.health.snapshot()['mode'] == 'primary':
            result = self.router.submit(payload, headers)
            if result.get('outcome') == 'acknowledged' and result.get('region') == self.router.recovery.name:
                self.health.enter_recovery('recovery_acknowledged')
            return result
        # Stay pinned to recovery until failback_if_ready() succeeds.
        region = self.router.recovery
        attempts = []
        with httpx.Client(timeout=10, transport=self.router.transport) as client:
            try:
                response = client.post(f"{region.url.rstrip('/')}/orders", json=payload, headers=headers)
                attempts.append({'region': region.name, 'status_code': response.status_code})
                if response.status_code in (401, 403, 409, 422):
                    return {'outcome': 'rejected', 'region': region.name,
                            'status_code': response.status_code, 'attempts': attempts}
                if response.status_code == 200:
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if (isinstance(body, dict) and body.get('status') in ('committed', 'duplicate')
                        and body.get('store_id') == headers['X-Store-ID']
                        and body.get('order_id') == payload['order_id']
                        and isinstance(body.get('receipt_id'), str) and body['receipt_id']):
                        return {'outcome': 'acknowledged', 'region': region.name,
                                'receipt_id': body['receipt_id'], 'attempts': attempts}
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                attempts.append({'region': region.name, 'error': type(exc).__name__})
        return {'outcome': 'unknown', 'region': region.name, 'attempts': attempts}
