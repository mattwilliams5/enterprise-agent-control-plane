"""Opt-in shared-Firestore signed store API. NOT deployed automatically.

Cloud-wide replay prevention requires all app instances to use the SAME
Firestore database. Provisioning keys is strictly out-of-band.
"""
import os
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from google.cloud import firestore

from applications.storeguard.cloud_dr.shared_store_identity import FirestoreStoreIdentityVerifier
from applications.storeguard.cloud_dr.store_identity import StoreAuthenticationError
from applications.storeguard.cloud_dr.order_ledger import FirestoreOrderLedger, IdempotencyConflict, Order

app = FastAPI(title='StoreGuard Shared-Identity Order API', docs_url=None,
              redoc_url=None, openapi_url=None)
SIGNED_HEADERS = (b'x-store-id', b'x-store-key-id', b'x-store-timestamp',
                  b'x-store-nonce', b'x-store-signature')


class OrderRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=128)
    amount_cents: int = Field(gt=0, le=100_000_000)
    idempotency_key: str = Field(min_length=1, max_length=128)


def get_cloud_components():
    project = os.getenv('GOOGLE_CLOUD_PROJECT')
    # Explicit opt-in prevents accidental use during local testing.
    if os.getenv('STOREGUARD_ENABLE_SHARED_IDENTITY') != 'I_ACKNOWLEDGE_FIRESTORE_WRITES' or not project:
        raise HTTPException(503, 'Shared identity backend not configured')
    client = firestore.Client(project=project, database='(default)')
    return FirestoreStoreIdentityVerifier(client), FirestoreOrderLedger(client)


@app.get('/health')
def health():
    return {'status': 'ok', 'authentication': 'shared-signed-only', 'backend': 'firestore'}


@app.post('/orders')
async def submit(request: Request, components=Depends(get_cloud_components)):
    raw_headers = request.scope['headers']
    if any(name.lower() == b'x-api-key' for name, _ in raw_headers):
        raise HTTPException(401, 'Invalid store credentials')
    if any(sum(name.lower() == required for name, _ in raw_headers) != 1 for required in SIGNED_HEADERS):
        raise HTTPException(401, 'Invalid store credentials')
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, 'Order request too large')
    verifier, ledger = components
    try:
        identity = verifier.verify(headers=dict(request.headers), method=request.method,
                                   path=request.url.path, body=body)
    except StoreAuthenticationError:
        raise HTTPException(401, 'Invalid store credentials') from None
    except Exception:
        raise HTTPException(503, 'Identity backend unavailable') from None
    try:
        payload = OrderRequest.model_validate_json(body)
        order = Order(identity.store_id, payload.order_id, payload.amount_cents,
                      payload.idempotency_key)
        order.validate()
    except (ValueError, ValidationError):
        raise HTTPException(422, 'Invalid order') from None
    try:
        return ledger.submit(order)
    except IdempotencyConflict:
        raise HTTPException(409, 'Idempotency conflict') from None
