"""Live StoreGuard agent runner assembly.

All authorization checks must be backed by trusted, authoritative
delegation and scope data. No permissive defaults are provided.
"""
from applications.storeguard.cloud_dr.cloud_governed_runner import (
    CloudGovernedReadOnlyRunner,
)
from applications.storeguard.cloud_dr.cloud_agent_authorizer import (
    CloudAgentAuthorizer,
)
from applications.storeguard.cloud_dr.firestore_agent_registry import (
    FirestoreAgentRegistry,
)
from applications.storeguard.cloud_dr.firestore_agent_audit import (
    FirestoreDecisionAudit,
)
from applications.storeguard.cloud_dr.firestore_tool_audit import (
    FirestoreToolAudit,
)
from applications.storeguard.cloud_dr.live_vault_identity import (
    LiveVaultIdentityVerifier,
)


PROJECT = "storeguard-dr-demo-2026"
DATABASE = "storeguard-executive-evidence"
VAULT_URL = "https://10.80.10.10:8200"
AGENT_SERVICE_ACCOUNT = (
    f"storeguard-agent-runtime@{PROJECT}.iam.gserviceaccount.com"
)


def build_live_runner(
    *,
    handlers,
    delegation_check,
    scope_check,
    certificate="/app/vault.crt",
):
    """Assemble the existing runner with real security adapters.

    Handlers and authorization callbacks must come from trusted
    backend code, never from incoming user requests.
    """
    if not callable(delegation_check):
        raise TypeError("Trusted delegation enforcement required")

    if not callable(scope_check):
        raise TypeError("Trusted incident/store scope enforcement required")

    registry = FirestoreAgentRegistry(
        project=PROJECT,
        database=DATABASE,
    )

    identity = LiveVaultIdentityVerifier(
        vault_url=VAULT_URL,
        certificate=certificate,
        service_account=AGENT_SERVICE_ACCOUNT,
        agent_bindings={
            "storeguard-weather-response-agent": AGENT_SERVICE_ACCOUNT,
            "sre-troubleshooting-agent": AGENT_SERVICE_ACCOUNT,
        },
    )

    authorizer = CloudAgentAuthorizer(
        registry=registry,
        delegation_check=delegation_check,
        scope_check=scope_check,
    )

    return CloudGovernedReadOnlyRunner(
        identity_verifier=identity,
        registry=registry,
        authorizer=authorizer,
        decision_audit=FirestoreDecisionAudit(
            project=PROJECT,
            database=DATABASE,
        ),
        tool_audit=FirestoreToolAudit(
            project=PROJECT,
            database=DATABASE,
        ),
        handlers=handlers,
    )
