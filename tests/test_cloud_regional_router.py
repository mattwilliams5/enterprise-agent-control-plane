import httpx

from applications.storeguard.cloud_dr.regional_router import (
    Region,
    RegionalRouter,
)


PRIMARY = Region("us-central1", "https://primary.example.test")
RECOVERY = Region("us-east4", "https://recovery.example.test")

PAYLOAD = {
    "order_id": "ORDER-1",
    "amount_cents": 2599,
    "idempotency_key": "KEY-1",
}
HEADERS = {
    "X-Store-ID": "1847",
    "X-API-Key": "test-only",
}


def router(handler):
    return RegionalRouter(
        PRIMARY,
        RECOVERY,
        transport=httpx.MockTransport(handler),
    )


def accepted():
    return httpx.Response(
        200,
        json={
            "status": "committed",
            "store_id": "1847",
            "order_id": "ORDER-1",
            "receipt_id": "a" * 64,
        },
    )


def test_primary_success():
    visited = []

    def handler(request):
        visited.append(request.url.host)
        return accepted()

    result = router(handler).submit(PAYLOAD, HEADERS)

    assert result["outcome"] == "acknowledged"
    assert result["region"] == "us-central1"
    assert visited == ["primary.example.test"]


def test_failover_on_primary_503():
    visited = []

    def handler(request):
        visited.append(request.url.host)
        if request.url.host == "primary.example.test":
            return httpx.Response(503)
        return accepted()

    result = router(handler).submit(PAYLOAD, HEADERS)

    assert result["outcome"] == "acknowledged"
    assert result["region"] == "us-east4"
    assert len(visited) == 2


def test_failover_on_timeout():
    def handler(request):
        if request.url.host == "primary.example.test":
            raise httpx.ReadTimeout("Simulated timeout")
        return accepted()

    result = router(handler).submit(PAYLOAD, HEADERS)

    assert result["outcome"] == "acknowledged"
    assert result["region"] == "us-east4"


def test_no_failover_on_403():
    visited = []

    def handler(request):
        visited.append(request.url.host)
        return httpx.Response(403)

    result = router(handler).submit(PAYLOAD, HEADERS)

    assert result["outcome"] == "rejected"
    assert visited == ["primary.example.test"]


def test_both_regions_unavailable():
    def handler(request):
        return httpx.Response(503)

    result = router(handler).submit(PAYLOAD, HEADERS)

    assert result["outcome"] == "unknown"
    assert len(result["attempts"]) == 2


def test_reject_insecure_remote_endpoint():
    import pytest

    with pytest.raises(ValueError):
        RegionalRouter(
            Region("primary", "http://remote.example.test"),
            RECOVERY,
        )
