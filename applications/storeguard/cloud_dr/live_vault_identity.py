"""Fresh Google IAM -> Vault identity verification for StoreGuard.

Only instantiate in a trusted Cloud Run workload. This module never
accepts Google credentials, JWTs, or Vault tokens from an API caller.
"""
import json
import time

import google.auth
from google.auth.transport.requests import AuthorizedSession
import requests

from applications.storeguard.cloud_dr.agent_execution_gate import VerifiedAgent


class LiveVaultIdentityVerifier:
    def __init__(self, *, vault_url, certificate, service_account,
                 agent_bindings, role="storeguard-agent"):
        if not vault_url.startswith("https://"):
            raise ValueError("Vault HTTPS required")
        if not agent_bindings:
            raise ValueError("Explicit agent bindings required")
        if any(email != service_account for email in agent_bindings.values()):
            raise ValueError("Agent binding mismatch")

        self.vault_url = vault_url.rstrip("/")
        self.certificate = certificate
        self.service_account = service_account
        self.agent_bindings = dict(agent_bindings)
        self.role = role

    def verify_fresh(self, evidence, *, run_id):
        """Perform an independent, live Vault login for every gate check."""
        agent_id = evidence

        if not isinstance(run_id, str) or not run_id:
            raise PermissionError("Missing run ID")
        if agent_id not in self.agent_bindings:
            raise PermissionError("Unregistered workload binding")

        # Verify the actual Cloud Run service account.
        metadata = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/"
            "instance/service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
            timeout=10,
        )
        metadata.raise_for_status()

        actual_email = metadata.text.strip()
        if actual_email != self.service_account:
            raise PermissionError("Unexpected runtime service account")

        if self.agent_bindings[agent_id] != actual_email:
            raise PermissionError("Agent workload binding mismatch")

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = AuthorizedSession(credentials)

        claims = {
            "sub": self.service_account,
            "aud": f"vault/{self.role}",
            "iat": int(time.time()),
            "exp": int(time.time()) + 240,
        }

        signed = session.post(
            "https://iamcredentials.googleapis.com/v1/"
            f"projects/-/serviceAccounts/{self.service_account}:signJwt",
            json={"payload": json.dumps(claims)},
            timeout=20,
        )
        signed.raise_for_status()

        login = requests.post(
            f"{self.vault_url}/v1/auth/gcp/login",
            json={
                "role": self.role,
                "jwt": signed.json()["signedJwt"],
            },
            verify=self.certificate,
            timeout=20,
        )
        login.raise_for_status()

        response = login.json()
        auth = response["auth"]
        token = auth["client_token"]

        try:
            metadata = auth.get("metadata") or {}
            entity_id = auth.get("entity_id")
            policies = auth.get("policies") or []
            ttl = int(auth.get("lease_duration", 0))
            request_id = response.get("request_id")

            if metadata.get("service_account_email") != self.service_account:
                raise PermissionError("Vault workload mismatch")
            if not isinstance(entity_id, str) or not entity_id:
                raise PermissionError("Missing Vault entity")
            if not request_id:
                raise PermissionError("Missing Vault request ID")
            if "storeguard-agent-minimal" not in policies or "default" in policies:
                raise PermissionError("Unexpected Vault policies")
            if not 0 < ttl <= 300:
                raise PermissionError("Invalid Vault credential lifetime")

            return VerifiedAgent(
                agent_id=agent_id,
                workload_subject=entity_id,
                evidence_id=request_id,
            )
        finally:
            # Verification does not grant a reusable Vault session.
            revoked = requests.post(
                f"{self.vault_url}/v1/auth/token/revoke-self",
                headers={"X-Vault-Token": token},
                verify=self.certificate,
                timeout=20,
            )
            revoked.raise_for_status()
