from unittest.mock import Mock, patch

import pytest

from identity.vault_identity import (
    VaultIdentityError,
    VaultRevocationError,
    managed_approle_session,
)


def mock_vault_client():
    client = Mock()
    client.auth.approle.login.return_value = {
        "auth": {
            "client_token": "test-token",
            "entity_id": "entity-123",
            "policies": ["storeguard-investigator"],
            "lease_duration": 300,
        }
    }
    return client


def open_session():
    return managed_approle_session(
        vault_addr="http://127.0.0.1:8200",
        role_id="test-role",
        secret_id="test-secret",
    )


def test_successful_session_revokes_token():
    client = mock_vault_client()

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with open_session() as identity:
            assert identity.entity_id == "entity-123"
            assert identity.token_ttl == 300

    client.auth.token.revoke_self.assert_called_once()


def test_failed_investigation_still_revokes_token():
    client = mock_vault_client()

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(RuntimeError, match="Investigation failed"):
            with open_session():
                raise RuntimeError("Investigation failed")

    client.auth.token.revoke_self.assert_called_once()


def test_identity_rejection_still_revokes_token():
    client = mock_vault_client()
    client.auth.approle.login.return_value["auth"]["entity_id"] = None

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(VaultIdentityError):
            with open_session():
                pass

    client.auth.token.revoke_self.assert_called_once()


def test_revocation_failure_is_reported():
    client = mock_vault_client()
    client.auth.token.revoke_self.side_effect = RuntimeError("Vault unavailable")

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(VaultRevocationError):
            with open_session():
                pass

    client.auth.token.revoke_self.assert_called_once()
