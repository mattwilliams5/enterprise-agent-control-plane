
from contextlib import contextmanager


@contextmanager
def _successful_vault_session(identity, on_token_revoked):
    """Simulate successful Vault cleanup."""
    try:
        yield identity
    finally:
        if on_token_revoked is not None:
            on_token_revoked()


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
        "identity.execution_gate.managed_approle_session",
        return_value=__import__('contextlib').nullcontext(vault_identity),
    ):
        response = run_gate(tmp_path, lambda: {"healthy": True})

    assert response["result"] == {"healthy": True}


def test_out_of_scope_denied_before_execution(tmp_path, vault_identity):
    calls = []

    with patch(
        "identity.execution_gate.managed_approle_session",
        return_value=__import__('contextlib').nullcontext(vault_identity),
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
        "identity.execution_gate.managed_approle_session",
        side_effect=RuntimeError("Vault unavailable"),
    ):
        with pytest.raises(ExecutionDenied):
            run_gate(tmp_path, lambda: calls.append("executed"))

    assert calls == []


def test_investigation_failure_propagates(tmp_path, vault_identity):
    def fail():
        raise RuntimeError("Investigation failed")

    with patch(
        "identity.execution_gate.managed_approle_session",
        return_value=__import__('contextlib').nullcontext(vault_identity),
    ):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            run_gate(tmp_path, fail)


def test_audit_failure_blocks_investigation(tmp_path, vault_identity):
    """No successful authorization audit means no execution."""
    from unittest.mock import Mock

    runner = Mock()

    with patch(
        "identity.execution_gate.managed_approle_session",
        return_value=__import__('contextlib').nullcontext(vault_identity),
    ), patch(
        "identity.execution_gate._record",
        side_effect=OSError("Audit storage unavailable"),
    ):
        with pytest.raises(OSError, match="Audit storage unavailable"):
            run_gate(tmp_path, runner)

    runner.assert_not_called()


def test_successful_execution_records_full_lifecycle(tmp_path, vault_identity):
    """Every completed execution has an auditable lifecycle."""
    import sqlite3

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=lambda **kwargs: _successful_vault_session(
                vault_identity, kwargs.get("on_token_revoked")
            ),
    ):
        response = run_gate(
            tmp_path,
            lambda: {"status": "investigated"},
        )

    with sqlite3.connect(tmp_path / "audit.sqlite3") as db:
        events = db.execute(
            """
            SELECT event_type
            FROM execution_events
            WHERE run_id = ?
            ORDER BY timestamp, rowid
            """,
            (response["run_id"],),
        ).fetchall()

    assert [event[0] for event in events] == [
        "AUTHORIZED",
        "STARTED",
        "COMPLETED",
        "TOKEN_REVOKED",
    ]


def test_execution_events_share_registration_fingerprint(
    tmp_path, vault_identity
):
    import sqlite3
    from registry.fingerprint import registration_fingerprint

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=lambda **kwargs: _successful_vault_session(
                vault_identity, kwargs.get("on_token_revoked")
            ),
    ):
        response = run_gate(
            tmp_path,
            lambda: {"status": "investigated"},
        )

    with sqlite3.connect(tmp_path / "audit.sqlite3") as db:
        rows = db.execute(
            """
            SELECT event_type, registration_fingerprint
            FROM execution_events
            WHERE run_id = ?
            ORDER BY timestamp, rowid
            """,
            (response["run_id"],),
        ).fetchall()

    expected = registration_fingerprint(AGENT)

    assert [event_type for event_type, _ in rows] == [
        "AUTHORIZED",
        "STARTED",
        "COMPLETED",
        "TOKEN_REVOKED",
    ]
    assert all(fingerprint == expected for _, fingerprint in rows)


def test_gate_revokes_after_success(tmp_path, vault_identity):
    from contextlib import contextmanager
    from unittest.mock import Mock

    revoke = Mock()

    @contextmanager
    def session(**kwargs):
        try:
            yield vault_identity
        finally:
            revoke()

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=session,
    ):
        response = run_gate(
            tmp_path,
            lambda: {"status": "complete"},
        )

    assert response["result"]["status"] == "complete"
    revoke.assert_called_once()


def test_gate_revokes_after_authorization_denial(
    tmp_path, vault_identity
):
    from contextlib import contextmanager
    from unittest.mock import Mock

    revoke = Mock()
    runner = Mock()

    @contextmanager
    def session(**kwargs):
        try:
            yield vault_identity
        finally:
            revoke()

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=session,
    ):
        with pytest.raises(ExecutionDenied):
            run_gate(tmp_path, runner, store_id="9999")

    runner.assert_not_called()
    revoke.assert_called_once()


def test_gate_revokes_after_investigation_failure(
    tmp_path, vault_identity
):
    from contextlib import contextmanager
    from unittest.mock import Mock

    revoke = Mock()

    @contextmanager
    def session(**kwargs):
        try:
            yield vault_identity
        finally:
            revoke()

    def fail():
        raise RuntimeError("Investigation failed")

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=session,
    ):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            run_gate(tmp_path, fail)

    revoke.assert_called_once()


def test_gate_reports_revocation_failure(tmp_path, vault_identity):
    import sqlite3
    from contextlib import contextmanager

    from identity.vault_identity import VaultRevocationError

    @contextmanager
    def session(**kwargs):
        yield vault_identity
        raise VaultRevocationError("Revocation unconfirmed")

    with patch(
        "identity.execution_gate.managed_approle_session",
        side_effect=session,
    ):
        with pytest.raises(VaultRevocationError):
            run_gate(tmp_path, lambda: {"status": "complete"})

    with sqlite3.connect(tmp_path / "audit.sqlite3") as db:
        events = [
            row[0] for row in db.execute(
                "SELECT event_type FROM execution_events ORDER BY rowid"
            )
        ]

    assert events == [
        "AUTHORIZED",
        "STARTED",
        "COMPLETED",
        "REVOCATION_FAILED",
    ]
