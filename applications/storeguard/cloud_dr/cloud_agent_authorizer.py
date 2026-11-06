"""Cloud agent authorization using fresh shared registration state.

Requires trusted identity verification before this adapter is invoked.
Capabilities alone never grant permission. No tool execution occurs here.
"""
from policy.agent_capabilities import is_capability_declared


class CloudAgentAuthorizer:
    def __init__(self, *, registry, delegation_check, scope_check):
        if not callable(delegation_check) or not callable(scope_check):
            raise TypeError("Trusted delegation and scope checks required")
        if not callable(getattr(registry, "matches_identity", None)):
            raise TypeError("Identity-bound registry required")

        self.registry = registry
        self.delegation_check = delegation_check
        self.scope_check = scope_check

    def authorize(self, *, identity, intent, run_id):
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                run_id,
                identity.agent_id,
                identity.workload_subject,
                intent.agent_id,
                intent.incident_id,
                intent.store_id,
                intent.action,
                intent.delegation_id,
            )
        ):
            return False

        if identity.agent_id != intent.agent_id:
            return False

        if not is_capability_declared(intent.agent_id, intent.action):
            return False

        # Fresh authoritative lookup; never use the static local registry.
        if not self.registry.matches_identity(
            intent.agent_id, identity.workload_subject
        ):
            return False

        if self.delegation_check(
            identity=identity, intent=intent, run_id=run_id
        ) is not True:
            return False

        return self.scope_check(
            identity=identity, intent=intent, run_id=run_id
        ) is True
