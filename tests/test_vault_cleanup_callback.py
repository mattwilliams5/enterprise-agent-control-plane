"""Verify managed Vault cleanup callbacks and failure handling."""

from unittest.mock import Mock, patch

import pytest

from identity.vault_identity import (
    VaultRevocationError,
    managed_approle_session,
)


def fake_client(*, revoke_fails=False):
    client = Mock()
    client.auth.approle.login.return_value = {
        "auth": {
            "client_token": "test-only-token",
            "entity_id": "test-entity",
            "policies": ["storeguard-investigator"],
            "lease_duration": 300,
        }
    }

    if revoke_fails:
        client.auth.token.revoke_self.side_effect = RuntimeError(
            "Vault unavailable"
        )

    return client


def test_cleanup_callback_runs_after_investigation_exception():
    client = fake_client()
    callback = Mock()

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            with managed_approle_session(
                vault_addr="http://127.0.0.1:8200",
                role_id="test-role",
                secret_id="test-secret",
                on_token_revoked=callback,
            ):
                raise RuntimeError("Investigation failed")

    client.auth.token.revoke_self.assert_called_once()
    callback.assert_called_once()


def test_cleanup_callback_does_not_run_when_revocation_fails():
    client = fake_client(revoke_fails=True)
    callback = Mock()

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(VaultRevocationError):
            with managed_approle_session(
                vault_addr="http://127.0.0.1:8200",
                role_id="test-role",
                secret_id="test-secret",
                on_token_revoked=callback,
            ):
                pass

    client.auth.token.revoke_self.assert_called_once()
    callback.assert_not_called()


def test_cleanup_callback_failure_does_not_claim_revocation_failure():
    """An audit callback error is distinct from a Vault revocation error."""
    client = fake_client()
    callback = Mock(side_effect=OSError("Audit database unavailable"))

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(OSError, match="Audit database unavailable"):
            with managed_approle_session(
                vault_addr="http://127.0.0.1:8200",
                role_id="test-role",
                secret_id="test-secret",
                on_token_revoked=callback,
            ):
                pass

    client.auth.token.revoke_self.assert_called_once()
    callback.assert_called_once()
