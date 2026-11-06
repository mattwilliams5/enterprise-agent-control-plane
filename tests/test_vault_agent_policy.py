"""Security regression tests for agent-specific Vault policies."""

from unittest.mock import MagicMock, patch

import pytest

from identity.vault_identity import (
    VaultIdentityError,
    managed_approle_session,
)


ENTITY_ID = "260976f6-efa7-1bfe-d002-d28e58640e71"
WEATHER_POLICY = "storeguard-weather-readonly"
SRE_POLICY = "storeguard-investigator"


def fake_vault_client(policies):
    client = MagicMock()
    client.auth.approle.login.return_value = {
        "request_id": "test-login-request",
        "auth": {
            "client_token": "test-token-not-real",
            "entity_id": ENTITY_ID,
            "policies": policies,
            "lease_duration": 300,
        },
    }
    return client


def open_weather_session(client):
    return managed_approle_session(
        vault_addr="http://vault.test:8200",
        role_id="test-role",
        secret_id="test-secret",
        required_policy=WEATHER_POLICY,
    )


def test_weather_policy_accepted():
    client = fake_vault_client([WEATHER_POLICY])

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with open_weather_session(client) as identity:
            assert identity.entity_id == ENTITY_ID
            assert identity.policies == (WEATHER_POLICY,)

    client.auth.token.revoke_self.assert_called_once()


@pytest.mark.parametrize(
    "policies",
    [
        [SRE_POLICY],
        [WEATHER_POLICY, SRE_POLICY],
        [WEATHER_POLICY, "default"],
        [],
    ],
)
def test_unexpected_weather_policies_denied_and_token_revoked(policies):
    client = fake_vault_client(policies)

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(VaultIdentityError):
            with open_weather_session(client):
                pytest.fail("Unauthorized session reached execution")

    client.auth.token.revoke_self.assert_called_once()


def test_missing_required_policy_denied_and_token_revoked():
    client = fake_vault_client([WEATHER_POLICY])

    with patch("identity.vault_identity.hvac.Client", return_value=client):
        with pytest.raises(VaultIdentityError):
            with managed_approle_session(
                vault_addr="http://vault.test:8200",
                role_id="test-role",
                secret_id="test-secret",
                required_policy="",
            ):
                pytest.fail("Empty policy requirement accepted")

    client.auth.token.revoke_self.assert_called_once()
