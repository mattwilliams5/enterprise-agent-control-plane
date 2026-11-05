"""Explicitly offline local-socket StoreGuard signed API; never deploy this demo ledger.

Run with uvicorn bound to 127.0.0.1 ONLY. The actual signature verification
is unchanged and delegated to signed_order_api.py. Zero Firestore access.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from applications.storeguard.cloud_dr.signed_order_api import app, get_ledger_factory
from applications.storeguard.cloud_dr.order_ledger import IdempotencyConflict


class OfflineSQLiteLedger:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.parent.is_dir():
            raise FileNotFoundError('Offline ledger parent directory missing')
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        db.execute('PRAGMA busy_timeout=15000')
        return db

    def _initialize(self):
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS demo_orders (
                store_id TEXT NOT NULL, order_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL, receipt_id TEXT NOT NULL,
                PRIMARY KEY (store_id, order_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS demo_keys (
                store_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                order_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,
                receipt_id TEXT NOT NULL,
                PRIMARY KEY (store_id, idempotency_key))''')

    def submit(self, order):
        order.validate()
        receipt = hashlib.sha256(json.dumps(
            [order.store_id, order.idempotency_key], separators=(',', ':')
        ).encode()).hexdigest()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                key = db.execute('SELECT order_id, amount_cents, receipt_id FROM demo_keys '
                                 'WHERE store_id=? AND idempotency_key=?',
                                 (order.store_id, order.idempotency_key)).fetchone()
                if key:
                    if key[:2] != (order.order_id, order.amount_cents):
                        raise IdempotencyConflict('Key conflict')
                    result = ('duplicate', key[2])
                else:
                    old = db.execute('SELECT amount_cents,receipt_id FROM demo_orders '
                                     'WHERE store_id=? AND order_id=?',
                                     (order.store_id, order.order_id)).fetchone()
                    if old and old[0] != order.amount_cents:
                        raise IdempotencyConflict('Logical order conflict')
                    if old:
                        result = ('duplicate', old[1])
                    else:
                        db.execute('INSERT INTO demo_orders VALUES (?,?,?,?)',
                                   (order.store_id, order.order_id, order.amount_cents, receipt))
                        result = ('committed', receipt)
                    db.execute('INSERT INTO demo_keys VALUES (?,?,?,?,?)',
                               (order.store_id, order.idempotency_key, order.order_id,
                                order.amount_cents, result[1]))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
        return {'status': result[0], 'store_id': order.store_id,
                'order_id': order.order_id, 'receipt_id': result[1]}


def offline_ledger_factory():
    path = os.environ.get('STOREGUARD_OFFLINE_LEDGER_DB')
    if not path:
        raise RuntimeError('STOREGUARD_OFFLINE_LEDGER_DB is required')
    return OfflineSQLiteLedger(path)


# Module is deliberately an explicit different ASGI target from signed_order_api.
app.dependency_overrides[get_ledger_factory] = lambda: offline_ledger_factory


@app.get('/demo-backend')
def demo_backend():
    """Local-only marker so fleet client never mistakes demo ledger for Firestore."""
    return {'backend': 'offline-sqlite-demo'}
