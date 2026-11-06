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
    login_request_id: str | None = None


def authenticate_approle(
    *,
    vault_addr: str,
    role_id: str,
    secret_id: str,
    required_policy: str = "storeguard-investigator",
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
        if not required_policy or set(policies) != {required_policy}:
            raise VaultIdentityError("Unexpected Vault token policies")

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


from contextlib import contextmanager


class VaultRevocationError(VaultIdentityError):
    """Vault token cleanup could not be confirmed."""


@contextmanager
def managed_approle_session(
    *,
    vault_addr: str,
    role_id: str,
    secret_id: str,
    required_policy: str = "storeguard-investigator",
    on_token_revoked=None,
):
    """Authenticate and manage a short-lived Vault token.

    The token remains inside this trusted backend context.
    The caller receives only verified identity metadata.
    """
    if not all((vault_addr, role_id, secret_id)):
        raise VaultIdentityError("Missing Vault authentication configuration")

    client = hvac.Client(url=vault_addr)
    token_issued = False

    try:
        response = client.auth.approle.login(
            role_id=role_id,
            secret_id=secret_id,
        )
        auth = response["auth"]
        token = auth.get("client_token")

        if not token:
            raise VaultIdentityError("Vault returned no client token")

        token_issued = True
        client.token = token

        entity_id = auth.get("entity_id")
        policies = tuple(auth.get("policies", []))
        ttl = int(auth.get("lease_duration", 0))

        if not entity_id:
            raise VaultIdentityError("Vault returned no entity identity")
        if not required_policy or set(policies) != {required_policy}:
            raise VaultIdentityError("Unexpected Vault token policies")
        if ttl <= 0:
            raise VaultIdentityError("Vault returned an invalid token TTL")

        yield VerifiedVaultIdentity(
            entity_id=entity_id,
            policies=policies,
            token_ttl=ttl,
            login_request_id=response.get("request_id"),
        )

    finally:
        if token_issued:
            try:
                client.auth.token.revoke_self()
            except Exception as exc:
                raise VaultRevocationError(
                    "Vault token revocation could not be confirmed"
                ) from exc
            else:
                if on_token_revoked is not None:
                    on_token_revoked()
