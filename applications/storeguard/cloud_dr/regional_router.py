"""Bounded, client-side regional routing for StoreGuard."""

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class Region:
    name: str
    url: str


class RegionalRouter:
    def __init__(self, primary, recovery, transport=None):
        if primary.name == recovery.name:
            raise ValueError("Regions must have different names")

        for region in (primary, recovery):
            parsed = urlparse(region.url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError("Invalid region endpoint")

            if parsed.scheme == "http" and parsed.hostname not in (
                "localhost",
                "127.0.0.1",
            ):
                raise ValueError("Remote endpoints require HTTPS")

        self.primary = primary
        self.recovery = recovery
        self.transport = transport

    def submit(self, payload, headers):
        attempts = []

        with httpx.Client(
            timeout=10,
            transport=self.transport,
        ) as client:
            for region in (self.primary, self.recovery):
                try:
                    response = client.post(
                        f"{region.url.rstrip('/')}/orders",
                        json=payload,
                        headers=headers,
                    )

                    attempts.append({
                        "region": region.name,
                        "status_code": response.status_code,
                    })

                    # Never fail over on an authorization failure,
                    # validation error, or conflicting transaction.
                    if response.status_code in (401, 403, 409, 422):
                        return {
                            "outcome": "rejected",
                            "region": region.name,
                            "attempts": attempts,
                            "status_code": response.status_code,
                        }

                    if response.status_code == 200:
                        body = response.json()
                        if (
                            body.get("status") in ("committed", "duplicate")
                            and body.get("order_id") == payload["order_id"]
                            and body.get("store_id") == headers["X-Store-ID"]
                            and isinstance(body.get("receipt_id"), str)
                        ):
                            return {
                                "outcome": "acknowledged",
                                "region": region.name,
                                "receipt_id": body["receipt_id"],
                                "attempts": attempts,
                            }

                        return {
                            "outcome": "unknown",
                            "region": region.name,
                            "attempts": attempts,
                        }

                    # A server-side failure may have occurred after commit.
                    # Retrying the SAME order identity is required.
                    if response.status_code not in (502, 503, 504):
                        return {
                            "outcome": "unknown",
                            "region": region.name,
                            "attempts": attempts,
                        }

                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    attempts.append({
                        "region": region.name,
                        "error": type(exc).__name__,
                    })

        return {
            "outcome": "unknown",
            "attempts": attempts,
        }
