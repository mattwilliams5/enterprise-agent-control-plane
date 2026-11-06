"""Authenticated, Ed25519-signed private Cloud Run failover for a demo order.

This sends a real signed order. A simulated primary outage is an explicit
client-side fault injection; it does NOT interrupt the deployed primary service.
Do not use this module for production traffic without operational review.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from applications.storeguard.cloud_dr.store_identity import sign_order_request


@dataclass(frozen=True)
class PrivateRegion:
    name: str
    url: str

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise ValueError("Private Cloud Run regions require an origin HTTPS URL")


def cloud_run_identity_token(audience: str) -> str:
    """Obtain a fresh Google OIDC token for the exact target service URL.

    The caller must run under a principal authorized as run.invoker on that
    service; no static bearer token is stored in configuration or Firestore.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token
    return fetch_id_token(Request(), audience)


def submit_signed_failover(
    *, primary: PrivateRegion, recovery: PrivateRegion,
    store_id: str, key_id: str, private_key: Ed25519PrivateKey,
    order_id: str, amount_cents: int, idempotency_key: str,
    identity_token=cloud_run_identity_token, transport=None,
    simulate_primary_outage: bool = False,
):
    """Return a receipt only if authenticated store and order fields match.

    Each HTTP delivery attempt gets a NEW Ed25519 nonce/signature while the
    logical order ID and idempotency key remain fixed. Sign the *exact* bytes
    passed to httpx; never use `json=` after signing. 401/403/409/422 are
    terminal and do not trigger region switching. A timeout may mean commit:
    both regions must share the same idempotent order ledger.
    """
    if primary.name == recovery.name or primary.url == recovery.url:
        raise ValueError("Primary and recovery must be distinct")
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("A trusted Ed25519 private key is required")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValueError("Invalid order amount")
    if not all(isinstance(x, str) and x for x in (order_id, idempotency_key, store_id, key_id)):
        raise ValueError("Missing order or store identity")

    payload = {"order_id": order_id, "amount_cents": amount_cents,
               "idempotency_key": idempotency_key}
    # Stable body bytes across retries AND regions.
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    attempts = []
    with httpx.Client(timeout=10, transport=transport, follow_redirects=False) as client:
        for region in (primary, recovery):
            if region is primary and simulate_primary_outage:
                attempts.append({"region": primary.name, "error": "SIMULATED_CLIENT_SIDE_OUTAGE"})
                continue
            # Always bind OIDC audience to the service actually contacted.
            token = identity_token(region.url.rstrip("/"))
            if not isinstance(token, str) or not token:
                raise RuntimeError("No private service identity token available")
            signed_headers = sign_order_request(
                private_key, store_id=store_id, key_id=key_id, body=body
            )
            headers = {**signed_headers, "Authorization": f"Bearer {token}",
                       "Content-Type": "application/json"}
            try:
                response = client.post(region.url.rstrip("/") + "/orders",
                                       content=body, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                attempts.append({"region": region.name, "error": type(error).__name__})
                continue
            status = response.status_code
            attempts.append({"region": region.name, "status_code": status})
            if status in (401, 403, 409, 422):
                return {"outcome": "rejected", "region": region.name,
                        "status_code": status, "attempts": attempts}
            if status == 200:
                try:
                    receipt = response.json()
                except ValueError:
                    receipt = None
                if (isinstance(receipt, dict)
                    and receipt.get("status") in ("committed", "duplicate")
                    and receipt.get("order_id") == order_id
                    and receipt.get("store_id") == store_id
                    and isinstance(receipt.get("receipt_id"), str)
                    and bool(receipt["receipt_id"])):
                    return {"outcome": "acknowledged", "region": region.name,
                            "order_id": order_id, "store_id": store_id,
                            "receipt_id": receipt["receipt_id"],
                            "primary_outage_simulated": simulate_primary_outage,
                            "attempts": attempts}
                return {"outcome": "unknown", "region": region.name, "attempts": attempts}
            if status not in (502, 503, 504):
                return {"outcome": "unknown", "region": region.name,
                        "status_code": status, "attempts": attempts}
    return {"outcome": "unknown", "attempts": attempts}
