"""Opt-in local Ed25519-only order API. Do NOT expose as a public Cloud Run service.

Uses the Batch 5 SQLite public-key registry/replay store. For a two-region
service, replace that local state with a consistent shared registry and
atomic replay store before deployment. Existing order_api.py is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from applications.storeguard.cloud_dr.store_identity import (
    StoreAuthenticationError, StoreIdentityRegistry,
)

app = FastAPI(title="StoreGuard Signed-Only Local Order API", docs_url=None,
              redoc_url=None, openapi_url=None)

MAX_BODY_BYTES = 16 * 1024
SIGNED_HEADERS = (
    b"x-store-id", b"x-store-key-id", b"x-store-timestamp",
    b"x-store-nonce", b"x-store-signature",
)


class OrderRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=128)
    amount_cents: int = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=1, max_length=128)


def get_registry_path() -> Path:
    path = os.environ.get("STOREGUARD_IDENTITY_DB")
    if not path:
        raise HTTPException(503, "Store identity registry not configured")
    registry_path = Path(path)
    # Never silently create an empty trust store when starting the API.
    if not registry_path.is_file():
        raise HTTPException(503, "Store identity registry unavailable")
    return registry_path


def get_ledger():
    # Delayed imports make it explicit that no Firestore client is needed for
    # failed authentication or local health checks.
    from applications.storeguard.cloud_dr.order_ledger import FirestoreOrderLedger
    from google.cloud import firestore
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise HTTPException(503, "Cloud project not configured")
    return FirestoreOrderLedger(client=firestore.Client(project=project, database="(default)"))


def get_ledger_factory():
    return get_ledger


@app.get("/health")
def health():
    return {"status": "ok", "authentication": "signed-only-local"}


@app.post("/orders")
async def submit_signed_order(
    request: Request,
    registry_path: Path = Depends(get_registry_path),
    ledger_factory=Depends(get_ledger_factory),
):
    # Prevent proxy/header normalization from hiding ambiguous duplicate IDs.
    raw_headers = request.scope["headers"]
    for required in SIGNED_HEADERS:
        if sum(name.lower() == required for name, _ in raw_headers) != 1:
            raise HTTPException(401, "Invalid store credentials")
    if any(name.lower() == b"x-api-key" for name, _ in raw_headers):
        raise HTTPException(401, "Development API key not supported")

    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        raise HTTPException(413, "Order request too large")

    # Each request gets its own SQLite connection (thread-safe across requests).
    registry = StoreIdentityRegistry(registry_path)
    try:
        try:
            verified = registry.verify(
                headers=dict(request.headers), method=request.method,
                path=request.url.path, body=raw_body,
            )
        except StoreAuthenticationError:
            raise HTTPException(401, "Invalid store credentials") from None
    finally:
        registry.close()

    # Parse *after* the exact signed body has been verified.
    try:
        payload = OrderRequest.model_validate_json(raw_body)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid order") from None

    from applications.storeguard.cloud_dr.order_ledger import (
        IdempotencyConflict, Order,
    )
    try:
        order = Order(
            store_id=verified.store_id,
            order_id=payload.order_id,
            amount_cents=payload.amount_cents,
            idempotency_key=payload.idempotency_key,
        )
        order.validate()
        return ledger_factory().submit(order)
    except IdempotencyConflict:
        raise HTTPException(409, "Idempotency conflict") from None
    except ValueError:
        raise HTTPException(422, "Invalid order") from None
