"""Verify Vault token access before and after managed-session cleanup."""

from unittest.mock import patch

import hvac
from hvac.exceptions import Forbidden, InvalidPath, InvalidRequest

from identity.vault_identity import managed_approle_session
from scripts.show_id_demo import VAULT_ADDR, fresh_credentials


role_id, secret_id = fresh_credentials()

real_client = hvac.Client
clients = []


def capture_client(*args, **kwargs):
    client = real_client(*args, **kwargs)
    clients.append(client)
    return client


with patch("identity.vault_identity.hvac.Client", side_effect=capture_client):
    with managed_approle_session(
        vault_addr=VAULT_ADDR,
        role_id=role_id,
        secret_id=secret_id,
    ) as identity:
        assert identity.entity_id
        assert len(clients) == 1

        client = clients[0]

        # This is an operation explicitly allowed by our Vault policy.
        client.secrets.kv.v2.read_secret_version(
            path="storeguard/operations",
            mount_point="secret",
            raise_on_deleted_version=True,
        )

        print("PASS: Token can read approved operations during session")

client = clients[0]

try:
    client.secrets.kv.v2.read_secret_version(
        path="storeguard/operations",
        mount_point="secret",
        raise_on_deleted_version=True,
    )
except (Forbidden, InvalidRequest):
    print("PASS: Token cannot access operations after revocation")
else:
    raise AssertionError(
        "SECURITY FAILURE: Revoked token still has operational access"
    )
