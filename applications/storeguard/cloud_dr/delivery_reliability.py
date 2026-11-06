"""Additive SQLite claims, retry schedules, and quarantine for the StoreGuard queue.

Does not change OrderQueue or its original orders schema. Every operation
uses a separate SQLite connection and BEGIN IMMEDIATE for safe atomic claims.
No automatic queue migration; existing pending orders are eligible.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClaimedOrder:
    store_id: str
    order_id: str
    amount_cents: int
    idempotency_key: str
    claim_token: str


class DeliveryState:
    def __init__(self, db_path, *, clock=None, busy_timeout_ms=5000):
        self.path = Path(db_path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Queue database missing: {self.path}")
        self.clock = clock or time.time
        self.db = sqlite3.connect(self.path, timeout=busy_timeout_ms / 1000, isolation_level=None)
        self.db.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        # A second, additive table. Existing queue schema/data is unchanged.
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS delivery_state (
                store_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                claim_token TEXT,
                lease_expires REAL,
                next_attempt REAL NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                disposition TEXT NOT NULL DEFAULT 'ready',
                last_outcome TEXT,
                last_status_code INTEGER,
                PRIMARY KEY (store_id, order_id),
                CHECK (disposition IN ('ready', 'quarantined'))
            )
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_delivery_claim ON delivery_state(disposition, next_attempt, lease_expires)")

    def close(self):
        self.db.close()

    def _begin(self):
        self.db.execute('BEGIN IMMEDIATE')

    def claim(self, *, lease_seconds=120):
        if lease_seconds <= 0:
            raise ValueError('lease_seconds must be positive')
        now = float(self.clock())
        try:
            self._begin()
            row = self.db.execute("""
                SELECT o.store_id, o.order_id, o.amount_cents, o.idempotency_key
                FROM orders o
                LEFT JOIN delivery_state s ON s.store_id=o.store_id AND s.order_id=o.order_id
                WHERE o.status='pending'
                  AND (s.disposition IS NULL OR s.disposition='ready')
                  AND (s.next_attempt IS NULL OR s.next_attempt<=?)
                  AND (s.claim_token IS NULL OR s.lease_expires<=?)
                ORDER BY o.store_id, o.order_id LIMIT 1
            """, (now, now)).fetchone()
            if row is None:
                self.db.execute('COMMIT')
                return None
            store_id, order_id, amount, key = row
            token = uuid.uuid4().hex
            self.db.execute("""
                INSERT INTO delivery_state (store_id, order_id, claim_token, lease_expires)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(store_id, order_id) DO UPDATE SET
                    claim_token=excluded.claim_token,
                    lease_expires=excluded.lease_expires
            """, (store_id, order_id, token, now + lease_seconds))
            self.db.execute('COMMIT')
            return ClaimedOrder(store_id, order_id, amount, key, token)
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def settle(self, claim: ClaimedOrder, *, outcome: str, receipt_id=None,
               status_code=None, base_delay=2, max_delay=300):
        """Atomic completion; stale workers cannot mutate newer claims.

        acknowledged: commit original order and clear claim transactionally.
        rejected/no_credentials: durable quarantine, no blind retries.
        unknown: backoff and replay original key on later claim.
        """
        if outcome not in ('acknowledged', 'rejected', 'no_credentials', 'unknown'):
            raise ValueError('Invalid outcome')
        if outcome == 'acknowledged' and (not isinstance(receipt_id, str) or not receipt_id):
            raise ValueError('Nonempty receipt required for acknowledgment')
        if base_delay <= 0 or max_delay < base_delay:
            raise ValueError('Invalid backoff')
        now = float(self.clock())
        try:
            self._begin()
            row = self.db.execute("""
                SELECT attempts FROM delivery_state
                WHERE store_id=? AND order_id=? AND claim_token=? AND disposition='ready'
                  AND lease_expires>?
            """, (claim.store_id, claim.order_id, claim.claim_token, now)).fetchone()
            if row is None:
                self.db.execute('COMMIT')
                return False
            attempts = row[0] + 1
            if outcome == 'acknowledged':
                updated = self.db.execute("""
                    UPDATE orders SET status='committed', receipt_id=?
                    WHERE store_id=? AND order_id=? AND status='pending'
                      AND amount_cents=? AND idempotency_key=?
                """, (receipt_id, claim.store_id, claim.order_id,
                      claim.amount_cents, claim.idempotency_key))
                if updated.rowcount != 1:
                    raise RuntimeError('Order no longer matches claimed payload')
            delay = min(max_delay, base_delay * 2 ** min(attempts - 1, 30))
            quarantine = outcome in ('rejected', 'no_credentials')
            self.db.execute("""
                UPDATE delivery_state SET
                    claim_token=NULL, lease_expires=NULL,
                    attempts=?, next_attempt=?, disposition=?,
                    last_outcome=?, last_status_code=?
                WHERE store_id=? AND order_id=? AND claim_token=?
            """, (attempts, now + delay if outcome == 'unknown' else 0,
                  'quarantined' if quarantine else 'ready', outcome, status_code,
                  claim.store_id, claim.order_id, claim.claim_token))
            self.db.execute('COMMIT')
            return True
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def release_quarantine(self, store_id, order_id):
        """Explicit operator action only; recheck credentials/policy first."""
        try:
            self._begin()
            result = self.db.execute("""
                UPDATE delivery_state SET disposition='ready', next_attempt=0,
                    claim_token=NULL, lease_expires=NULL
                WHERE store_id=? AND order_id=? AND disposition='quarantined'
            """, (store_id, order_id))
            self.db.execute('COMMIT')
            return result.rowcount == 1
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def inspect(self, store_id, order_id):
        row = self.db.execute("""
            SELECT disposition, attempts, next_attempt, last_outcome,
                   last_status_code, claim_token, lease_expires
            FROM delivery_state WHERE store_id=? AND order_id=?
        """, (store_id, order_id)).fetchone()
        return dict(zip(('disposition', 'attempts', 'next_attempt', 'last_outcome',
                         'last_status_code', 'claim_token', 'lease_expires'), row)) if row else None
