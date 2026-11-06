"""Offline policy tests. Signature verification is mocked."""
from copy import deepcopy
import pytest
from applications.storeguard.cloud_dr.google_workload_identity import (
    GoogleWorkloadVerifier, WorkloadIdentityDenied,
)

AUD = "https://storeguard-agent.example.run.app"
EMAIL = "storeguard-agent-runtime@storeguard-dr-demo-2026.iam.gserviceaccount.com"
AGENT = "storeguard-weather-response-agent"


def claims():
    return {
        "iss": "https://accounts.google.com",
        "aud": AUD,
        "email": EMAIL,
        "email_verified": True,
        "sub": "123456789012345678901",
    }


def build(payload=None, failed=False):
    payload = deepcopy(claims() if payload is None else payload)
    calls = []

    def verify(token, request, audience):
        calls.append((token, audience))
        if failed:
            raise ValueError("signature invalid")
        return deepcopy(payload)

    return GoogleWorkloadVerifier(
        audience=AUD,
        agent_bindings={AGENT: EMAIL},
        token_verifier=verify,
    ), calls


def test_valid_identity():
    verifier, calls = build()
    result = verifier.verify(token="fixture", agent_id=AGENT)
    assert result.service_account_email == EMAIL
    assert result.agent_id == AGENT
    assert calls == [("fixture", AUD)]


def test_signature_failure_denied():
    verifier, _ = build(failed=True)
    with pytest.raises(WorkloadIdentityDenied):
        verifier.verify(token="bad", agent_id=AGENT)


def test_unbound_agent_denied():
    verifier, calls = build()
    with pytest.raises(WorkloadIdentityDenied):
        verifier.verify(token="fixture", agent_id="unknown")
    assert not calls


@pytest.mark.parametrize("field,value", [
    ("iss", "https://evil.example"),
    ("aud", "https://wrong.example"),
    ("email", "other@storeguard-dr-demo-2026.iam.gserviceaccount.com"),
    ("email_verified", False),
    ("email_verified", None),
    ("sub", ""),
    ("sub", None),
])
def test_invalid_claims_denied(field, value):
    payload = claims()
    payload[field] = value
    verifier, _ = build(payload)
    with pytest.raises(WorkloadIdentityDenied):
        verifier.verify(token="fixture", agent_id=AGENT)


@pytest.mark.parametrize("token", ["", None, 123])
def test_invalid_token_denied(token):
    verifier, _ = build()
    with pytest.raises(WorkloadIdentityDenied):
        verifier.verify(token=token, agent_id=AGENT)


def test_missing_bindings_rejected():
    with pytest.raises(ValueError):
        GoogleWorkloadVerifier(audience=AUD, agent_bindings={})


def test_http_audience_rejected():
    with pytest.raises(ValueError):
        GoogleWorkloadVerifier(
            audience="http://localhost", agent_bindings={AGENT: EMAIL}
        )


def test_personal_email_binding_rejected():
    with pytest.raises(ValueError):
        GoogleWorkloadVerifier(
            audience=AUD, agent_bindings={AGENT: "person@gmail.com"}
        )


def test_bindings_cannot_be_modified_externally():
    bindings = {AGENT: EMAIL}
    verifier = GoogleWorkloadVerifier(
        audience=AUD,
        agent_bindings=bindings,
        token_verifier=lambda *args, **kwargs: claims(),
    )
    bindings[AGENT] = "other@example.com"
    assert verifier.bindings[AGENT] == EMAIL


def test_invalid_verified_claims_type_denied():
    verifier, _ = build([])
    with pytest.raises(WorkloadIdentityDenied):
        verifier.verify(token="fixture", agent_id=AGENT)
