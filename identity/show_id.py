"""StoreGuard workload identity verification."""

from dataclasses import dataclass

from identity.vault_identity import VerifiedVaultIdentity
from registry.registry import get_agent_record


class IdentityDenied(PermissionError):
    """The workload is not an approved, verified agent."""


@dataclass(frozen=True)
class IdentityDecision:
    agent_name: str
    vault_entity_id: str
    verified: bool


def verify_agent_identity(
    agent_name: str,
    vault_identity: VerifiedVaultIdentity,
) -> IdentityDecision:
    record = get_agent_record(agent_name)

    if record is None:
        raise IdentityDenied("Agent is not registered")

    if not record.approved or record.status != "active":
        raise IdentityDenied("Agent is not approved and active")

    if not record.vault_entity_id:
        raise IdentityDenied("Agent has no trusted Vault identity binding")

    if record.vault_entity_id != vault_identity.entity_id:
        raise IdentityDenied("Vault identity does not match registered agent")

    return IdentityDecision(
        agent_name=agent_name,
        vault_entity_id=vault_identity.entity_id,
        verified=True,
    )
