"""Verify investigation and Vault cleanup failures are audited separately."""

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from identity.execution_gate import execute_investigation
from identity.vault_identity import (
    VaultRevocationError,
    VerifiedVaultIdentity,
)


IDENTITY = VerifiedVaultIdentity(
    entity_id="test-entity",
    policies=("storeguard-investigator",),
    token_ttl=300,
)


def audit_events(db_path):
    with sqlite3.connect(db_path) as db:
        return [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM execution_events ORDER BY rowid"
            )
        ]


def execute_test(tmp_path, *, cleanup_fails=False):
    db_path = tmp_path / "audit.sqlite3"

    @contextmanager
    def session(**kwargs):
        try:
            yield IDENTITY
        finally:
            if cleanup_fails:
                raise VaultRevocationError("Revocation unconfirmed")

    def investigation():
        raise RuntimeError("Investigation failed")

    with (
        patch(
            "identity.execution_gate.managed_approle_session",
            side_effect=session,
        ),
        patch("identity.execution_gate.verify_agent_identity"),
        patch(
            "identity.execution_gate.authorize_investigation",
            return_value=True,
        ),
    ):
        with pytest.raises(
            VaultRevocationError if cleanup_fails else RuntimeError
        ):
            execute_investigation(
                agent_name="sre-troubleshooting-agent",
                store_id="1847",
                incident_id="test-incident",
                vault_addr="http://127.0.0.1:8200",
                role_id="test-role",
                secret_id="test-secret",
                allowed_store_ids={"1847"},
                investigation=investigation,
                db_path=db_path,
            )

    return audit_events(db_path)


def test_investigation_failure_is_explicitly_audited(tmp_path):
    events = execute_test(tmp_path)

    assert events == [
        "AUTHORIZED",
        "STARTED",
        "INVESTIGATION_FAILED",
    ]


def test_investigation_and_revocation_failures_are_both_audited(tmp_path):
    events = execute_test(tmp_path, cleanup_fails=True)

    assert events == [
        "AUTHORIZED",
        "STARTED",
        "INVESTIGATION_FAILED",
        "REVOCATION_FAILED",
    ]


def test_investigation_failure_with_successful_revocation(tmp_path):
    """A failed investigation still records successful token cleanup."""
    db_path = tmp_path / "audit.sqlite3"

    @contextmanager
    def session(**kwargs):
        try:
            yield IDENTITY
        finally:
            callback = kwargs.get("on_token_revoked")
            if callback is not None:
                callback()

    def investigation():
        raise RuntimeError("Investigation failed")

    with (
        patch(
            "identity.execution_gate.managed_approle_session",
            side_effect=session,
        ),
        patch("identity.execution_gate.verify_agent_identity"),
        patch(
            "identity.execution_gate.authorize_investigation",
            return_value=True,
        ),
    ):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            execute_investigation(
                agent_name="sre-troubleshooting-agent",
                store_id="1847",
                incident_id="test-incident",
                vault_addr="http://127.0.0.1:8200",
                role_id="test-role",
                secret_id="test-secret",
                allowed_store_ids={"1847"},
                investigation=investigation,
                db_path=db_path,
            )

    assert audit_events(db_path) == [
        "AUTHORIZED",
        "STARTED",
        "INVESTIGATION_FAILED",
        "TOKEN_REVOKED",
    ]
