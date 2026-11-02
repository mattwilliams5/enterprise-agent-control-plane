"""Vault-backed workload authentication for StoreGuard."""

from dataclasses import dataclass

import hvac


class VaultIdentityError(RuntimeError):
    """Workload authentication failed."""


@dataclass(frozen=True)
class VerifiedVaultIdentity:
    entity_id: str
    policies: tuple[str, ...]
    token_ttl: int


def authenticate_approle(
    *,
    vault_addr: str,
    role_id: str,
    secret_id: str,
) -> VerifiedVaultIdentity:
    """Authenticate using a fresh AppRole SecretID.

    Does not return or log the Vault token.
    """
    if not all((vault_addr, role_id, secret_id)):
        raise VaultIdentityError("Missing Vault authentication configuration")

    client = hvac.Client(url=vault_addr)

    try:
        response = client.auth.approle.login(
            role_id=role_id,
            secret_id=secret_id,
        )
        auth = response["auth"]

        if not auth.get("client_token"):
            raise VaultIdentityError("Vault returned no client token")

        entity_id = auth.get("entity_id")
        if not entity_id:
            raise VaultIdentityError("Vault returned no entity identity")

        policies = tuple(auth.get("policies", []))
        if "storeguard-investigator" not in policies:
            raise VaultIdentityError("Required investigator policy missing")

        return VerifiedVaultIdentity(
            entity_id=entity_id,
            policies=policies,
            token_ttl=int(auth.get("lease_duration", 0)),
        )

    except VaultIdentityError:
        raise
    except Exception as exc:
        raise VaultIdentityError(
            "Vault workload authentication failed"
        ) from exc
