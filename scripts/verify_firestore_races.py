#!/usr/bin/env python3
"""Opt-in live Firestore concurrency check for StoreGuard's canonical order ledger.

This writes uniquely named synthetic test orders to the configured Firestore project.
It neither deploys services nor deletes documents. Run from the repository root.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import threading
from uuid import uuid4

from google.cloud import firestore
from applications.storeguard.cloud_dr.order_ledger import (
    FirestoreOrderLedger, IdempotencyConflict, Order,
)


def digest(*parts):
    return sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def run_pair(client, pair, run_id):
    barrier = threading.Barrier(2)

    def submit(order):
        barrier.wait(timeout=10)
        try:
            return {"kind": "result", "value": FirestoreOrderLedger(client=client).submit(order)}
        except IdempotencyConflict as exc:
            return {"kind": "conflict", "value": str(exc)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, o) for o in pair]
        return [future.result(timeout=90) for future in futures]


def read_state(client, store_id, order_id, keys):
    cid = digest(store_id, order_id)
    canonical = client.collection("storeguard_order_identity").document(cid).get()
    assert canonical.exists, "Missing canonical identity document"
    canonical_data = canonical.to_dict()
    assert canonical_data["store_id"] == store_id
    assert canonical_data["order_id"] == order_id
    receipt = client.collection("storeguard_orders").document(canonical_data["receipt_id"]).get()
    assert receipt.exists, "Missing referenced receipt document"
    key_docs = {
        key: client.collection("storeguard_order_keys").document(digest(store_id, key)).get()
        for key in keys
    }
    return canonical_data, receipt.to_dict(), key_docs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="Expected Google Cloud project ID")
    parser.add_argument("--ack-live-writes", action="store_true", help="Confirm synthetic Firestore writes")
    args = parser.parse_args()
    if not args.ack_live_writes:
        parser.error("Live Firestore writes require --ack-live-writes")
    if args.project != "storeguard-dr-demo-2026":
        parser.error("Refusing to write to an unexpected project")
    if os.environ.get("GOOGLE_CLOUD_PROJECT") != args.project:
        parser.error("Set GOOGLE_CLOUD_PROJECT to the expected project")

    client = firestore.Client(project=args.project)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10]
    store_id = "SGRACE" + uuid4().hex[:10]
    print("Cloud test:", args.project, "run:", run_id, "store:", store_id, flush=True)
    failures = []

    for label, amounts in (("same-payload-different-keys", (2599, 2599)),
                           ("different-amount-different-keys", (2599, 3999))):
        order_id = "RACE" + uuid4().hex[:16]
        keys = ["KEY" + uuid4().hex[:18] for _ in range(2)]
        pair = [Order(store_id, order_id, amounts[i], keys[i]) for i in range(2)]
        print("Testing", label, "order:", order_id, flush=True)
        try:
            outcomes = run_pair(client, pair, run_id)
            canonical, receipt, key_docs = read_state(client, store_id, order_id, keys)
            statuses = sorted(
                item["value"]["status"] if item["kind"] == "result" else item["kind"]
                for item in outcomes
            )
            if amounts[0] == amounts[1]:
                assert statuses == ["committed", "duplicate"], statuses
                assert all(snapshot.exists for snapshot in key_docs.values())
                assert all(snapshot.to_dict()["receipt_id"] == canonical["receipt_id"]
                           for snapshot in key_docs.values())
                assert all(item["value"]["receipt_id"] == canonical["receipt_id"]
                           for item in outcomes if item["kind"] == "result")
            else:
                assert statuses == ["committed", "conflict"], statuses
                assert sum(snapshot.exists for snapshot in key_docs.values()) == 1
                assert receipt["amount_cents"] in amounts
            assert receipt["order_id"] == order_id
            assert receipt["store_id"] == store_id
            print("PASS", label, statuses, "receipt:", canonical["receipt_id"], flush=True)
        except Exception as exc:
            print("FAIL", label, type(exc).__name__, str(exc), flush=True)
            failures.append((label, exc))

    if failures:
        raise SystemExit(f"{len(failures)} scenario(s) failed; inspect above output")
    print("PASS all live Firestore first-submission race scenarios", flush=True)
    print("Synthetic test documents intentionally retained for inspection.", flush=True)


if __name__ == "__main__":
    main()
