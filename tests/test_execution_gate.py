from unittest.mock import patch

import pytest

from identity.execution_gate import ExecutionDenied, execute_investigation
from identity.vault_identity import VerifiedVaultIdentity
from registry.registry import get_agent_record


AGENT = "sre-troubleshooting-agent"
ENTITY = get_agent_record(AGENT).vault_entity_id


@pytest.fixture
def vault_identity():
    return VerifiedVaultIdentity(
        entity_id=ENTITY,
        policies=("storeguard-investigator",),
        token_ttl=300,
    )


def run_gate(tmp_path, investigation, store_id="1847"):
    return execute_investigation(
        agent_name=AGENT,
        store_id=store_id,
        incident_id="INC-001",
        vault_addr="http://127.0.0.1:8200",
        role_id="test-role",
        secret_id="test-secret",
        allowed_store_ids=frozenset({"1847"}),
        investigation=investigation,
        db_path=tmp_path / "audit.sqlite3",
    )


def test_authorized_execution(tmp_path, vault_identity):
    with patch(
        "identity.execution_gate.authenticate_approle",
        return_value=vault_identity,
    ):
        response = run_gate(tmp_path, lambda: {"healthy": True})

    assert response["result"] == {"healthy": True}


def test_out_of_scope_denied_before_execution(tmp_path, vault_identity):
    calls = []

    with patch(
        "identity.execution_gate.authenticate_approle",
        return_value=vault_identity,
    ):
        with pytest.raises(ExecutionDenied):
            run_gate(
                tmp_path,
                lambda: calls.append("executed"),
                store_id="9999",
            )

    assert calls == []


def test_authentication_failure_denied(tmp_path):
    calls = []

    with patch(
        "identity.execution_gate.authenticate_approle",
        side_effect=RuntimeError("Vault unavailable"),
    ):
        with pytest.raises(ExecutionDenied):
            run_gate(tmp_path, lambda: calls.append("executed"))

    assert calls == []


def test_investigation_failure_propagates(tmp_path, vault_identity):
    def fail():
        raise RuntimeError("Investigation failed")

    with patch(
        "identity.execution_gate.authenticate_approle",
        return_value=vault_identity,
    ):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            run_gate(tmp_path, fail)
