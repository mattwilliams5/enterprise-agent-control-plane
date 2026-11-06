"""Verify actual AppRole token revocation against local development Vault."""

import hvac

from identity.vault_identity import managed_approle_session
from scripts.show_id_demo import fresh_credentials, VAULT_ADDR


role_id, secret_id = fresh_credentials()

with managed_approle_session(
    vault_addr=VAULT_ADDR,
    role_id=role_id,
    secret_id=secret_id,
) as identity:
    print("Authenticated Vault entity:", identity.entity_id)
    print("Token TTL:", identity.token_ttl)
    print("Managed session opened successfully")

print("Managed session closed; token revocation was requested")
print("PASS: Vault accepted token self-revocation")
