"""Durable SQLite queue for simulated StoreGuard clients."""

import json
import sqlite3
from pathlib import Path

import httpx


class OrderQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                store_id TEXT NOT NULL,
                order_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                receipt_id TEXT,
                PRIMARY KEY (store_id, order_id)
            )
        """)
        self.db.commit()

    def enqueue(self, order):
        from applications.storeguard.cloud_dr.order_ledger import Order

        validated = Order(
            order.store_id,
            order.order_id,
            order.amount_cents,
            order.idempotency_key,
        )
        validated.validate()

        self.db.execute("""
            INSERT OR IGNORE INTO orders
            (store_id, order_id, amount_cents, idempotency_key)
            VALUES (?, ?, ?, ?)
        """, (
            order.store_id,
            order.order_id,
            order.amount_cents,
            order.idempotency_key,
        ))
        self.db.commit()

        saved = self.db.execute("""
            SELECT amount_cents, idempotency_key
            FROM orders WHERE store_id=? AND order_id=?
        """, (order.store_id, order.order_id)).fetchone()

        if saved != (order.amount_cents, order.idempotency_key):
            raise ValueError("Conflicting queued order")

    def pending(self):
        rows = self.db.execute("""
            SELECT store_id, order_id, amount_cents, idempotency_key
            FROM orders WHERE status='pending'
            ORDER BY store_id, order_id
        """).fetchall()

        return [
            dict(zip(
                ("store_id", "order_id", "amount_cents", "idempotency_key"),
                row,
            ))
            for row in rows
        ]

    def acknowledge(self, store_id, order_id, receipt_id):
        with self.db:
            cursor = self.db.execute("""
                UPDATE orders
                SET status='committed', receipt_id=?
                WHERE store_id=? AND order_id=? AND status='pending'
            """, (receipt_id, store_id, order_id))
            if cursor.rowcount != 1:
                raise ValueError("Pending order not found")

    def close(self):
        self.db.close()


def deliver_pending(queue, base_url, credentials):
    results = []

    with httpx.Client(timeout=30) as client:
        for order in queue.pending():
            store_id = order["store_id"]

            if store_id not in credentials:
                results.append((order["order_id"], "no_credentials"))
                continue

            try:
                response = client.post(
                    f"{base_url.rstrip('/')}/orders",
                    headers={
                        "X-Store-ID": store_id,
                        "X-API-Key": credentials[store_id],
                    },
                    json={
                        "order_id": order["order_id"],
                        "amount_cents": order["amount_cents"],
                        "idempotency_key": order["idempotency_key"],
                    },
                )

                if response.status_code == 200:
                    body = response.json()
                    if (
                        body.get("status") in ("committed", "duplicate")
                        and body.get("store_id") == store_id
                        and body.get("order_id") == order["order_id"]
                        and isinstance(body.get("receipt_id"), str)
                    ):
                        queue.acknowledge(
                            store_id,
                            order["order_id"],
                            body["receipt_id"],
                        )
                        results.append((order["order_id"], "acknowledged"))
                    else:
                        results.append((order["order_id"], "invalid_response"))
                else:
                    results.append(
                        (order["order_id"], f"http_{response.status_code}")
                    )

            except (httpx.TimeoutException, httpx.TransportError):
                results.append((order["order_id"], "retry_pending"))

    return results
