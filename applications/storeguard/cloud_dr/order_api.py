"""Local development API for StoreGuard cloud order processing."""

import os
import re
import secrets
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from google.cloud import firestore
from pydantic import BaseModel, Field

from applications.storeguard.cloud_dr.order_ledger import (
    FirestoreOrderLedger,
    IdempotencyConflict,
    Order,
)

app = FastAPI(
    title="StoreGuard Order API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class OrderRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=128)
    amount_cents: int = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=1, max_length=128)


def authorized_store(
    x_store_id: str = Header(...),
    x_api_key: str = Header(...),
):
    configured_key = os.environ.get("STOREGUARD_DEV_API_KEY")
    configured_store = os.environ.get("STOREGUARD_DEV_STORE_ID")

    if not configured_key or not configured_store:
        raise HTTPException(503, "Development authentication not configured")

    if not secrets.compare_digest(x_api_key, configured_key):
        raise HTTPException(401, "Unauthorized")

    if not secrets.compare_digest(x_store_id, configured_store):
        raise HTTPException(403, "Store not authorized")

    return configured_store


@lru_cache(maxsize=1)
def get_ledger():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required")

    return FirestoreOrderLedger(
        client=firestore.Client(project=project, database="(default)")
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders")
def submit_order(
    request: OrderRequest,
    store_id: str = Depends(authorized_store),
    ledger: FirestoreOrderLedger = Depends(get_ledger),
):
    try:
        return ledger.submit(
            Order(
                store_id=store_id,
                order_id=request.order_id,
                amount_cents=request.amount_cents,
                idempotency_key=request.idempotency_key,
            )
        )
    except ValueError:
        raise HTTPException(422, "Invalid order")
    except IdempotencyConflict:
        raise HTTPException(409, "Idempotency conflict")


@app.get("/orders/{receipt_id}")
def get_order(
    receipt_id: str,
    store_id: str = Depends(authorized_store),
    ledger: FirestoreOrderLedger = Depends(get_ledger),
):
    if not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
        raise HTTPException(422, "Invalid receipt ID")

    snapshot = (
        ledger.client.collection("storeguard_orders")
        .document(receipt_id)
        .get()
    )

    if not snapshot.exists:
        raise HTTPException(404, "Order not found")

    order = snapshot.to_dict()

    if order.get("store_id") != store_id:
        raise HTTPException(404, "Order not found")

    return {
        "store_id": order["store_id"],
        "order_id": order["order_id"],
        "amount_cents": order["amount_cents"],
        "receipt_id": receipt_id,
    }
