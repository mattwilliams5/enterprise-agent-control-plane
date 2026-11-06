"""StoreGuard bounded retail order workload simulator."""

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

import httpx


STORE_IDS = tuple(str(number) for number in range(1847, 1887))


@dataclass(frozen=True)
class SimulatedOrder:
    store_id: str
    order_id: str
    amount_cents: int
    idempotency_key: str

    def payload(self):
        return {
            "order_id": self.order_id,
            "amount_cents": self.amount_cents,
            "idempotency_key": self.idempotency_key,
        }


def generate_orders(orders_per_store=2, seed=42):
    if not 1 <= orders_per_store <= 10:
        raise ValueError("orders_per_store must be between 1 and 10")

    rng = random.Random(seed)
    run_id = uuid4().hex[:12]

    return [
        SimulatedOrder(
            store_id=store_id,
            order_id=f"SG-{run_id}-{store_id}-{index:03d}",
            amount_cents=rng.randint(500, 25000),
            idempotency_key=f"SG-{run_id}-{store_id}-{index:03d}",
        )
        for store_id in STORE_IDS
        for index in range(orders_per_store)
    ]


def run_simulation(orders):
    results = []

    for order in orders:
        results.append({
            **asdict(order),
            "status": "simulated",
            "region": "local-simulation",
        })

    return results


def run_live(orders, base_url, key_path):
    key = Path(key_path).read_text().strip()

    if not key:
        raise ValueError("Development API key is empty")

    results = []

    with httpx.Client(timeout=30) as client:
        for order in orders:
            if order.store_id != "1847":
                raise ValueError(
                    "Live mode currently supports Store 1847 only"
                )

            started = time.monotonic()

            try:
                response = client.post(
                    f"{base_url}/orders",
                    headers={
                        "X-Store-ID": order.store_id,
                        "X-API-Key": key,
                    },
                    json=order.payload(),
                )

                elapsed_ms = round(
                    (time.monotonic() - started) * 1000, 2
                )

                if response.status_code != 200:
                    results.append({
                        "store_id": order.store_id,
                        "order_id": order.order_id,
                        "status": "http_error",
                        "http_status": response.status_code,
                        "latency_ms": elapsed_ms,
                    })
                    continue

                body = response.json()

                results.append({
                    "store_id": order.store_id,
                    "order_id": order.order_id,
                    "status": body["status"],
                    "receipt_id": body["receipt_id"],
                    "latency_ms": elapsed_ms,
                })

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                results.append({
                    "store_id": order.store_id,
                    "order_id": order.order_id,
                    "status": "unknown",
                    "error_type": type(exc).__name__,
                })

    return results


def summarize(results):
    counts = {}

    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1

    return {
        "total": len(results),
        "stores": len({r["store_id"] for r in results}),
        "statuses": counts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["simulate", "live"],
        default="simulate",
    )
    parser.add_argument("--orders-per-store", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
    )
    parser.add_argument(
        "--key-file",
        default=".local/storeguard-dev-api-key",
    )
    args = parser.parse_args()

    orders = generate_orders(args.orders_per_store, args.seed)

    if args.mode == "live":
        # Deliberately bounded: no multi-store impersonation.
        orders = [order for order in orders if order.store_id == "1847"]
        if args.base_url.rstrip("/") != "http://127.0.0.1:8080":
            parser.error("Live development mode requires localhost:8080")

        results = run_live(
            orders,
            args.base_url,
            args.key_file,
        )
    else:
        results = run_simulation(orders)

    print(json.dumps(summarize(results), indent=2))

    failures = [
        r for r in results
        if r["status"] in {"unknown", "http_error"}
    ]
    if failures:
        print(json.dumps(failures, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
