"""Google-signed workload identity verifier. No Vault access or secrets."""
from dataclasses import dataclass
from types import MappingProxyType
from google.auth.transport.requests import Request
from google.oauth2 import id_token


class WorkloadIdentityDenied(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedCloudWorkload:
    agent_id: str
    service_account_email: str
    subject: str
    issuer: str
    audience: str


class GoogleWorkloadVerifier:
    def __init__(self, *, audience, agent_bindings, token_verifier=None):
        if not isinstance(audience, str) or not audience.startswith("https://"):
            raise ValueError("HTTPS audience required")
        if not isinstance(agent_bindings, dict) or not agent_bindings:
            raise ValueError("Explicit agent bindings required")
        for agent, email in agent_bindings.items():
            if not isinstance(agent, str) or not agent.strip():
                raise ValueError("Invalid agent ID")
            if not (isinstance(email, str)
                    and email.endswith(".iam.gserviceaccount.com")
                    and "@" in email and email == email.lower()):
                raise ValueError("Invalid service account")
        self.audience = audience
        self.bindings = MappingProxyType(dict(agent_bindings))
        self.token_verifier = token_verifier or id_token.verify_oauth2_token

    def verify(self, *, token, agent_id):
        if not isinstance(token, str) or not token.strip():
            raise WorkloadIdentityDenied("Missing identity token")
        if agent_id not in self.bindings:
            raise WorkloadIdentityDenied("Agent is not workload-bound")
        try:
            claims = self.token_verifier(
                token, Request(), audience=self.audience
            )
        except Exception as exc:
            raise WorkloadIdentityDenied("Token verification failed") from exc

        if not isinstance(claims, dict):
            raise WorkloadIdentityDenied("Invalid claims")
        if claims.get("iss") not in (
            "accounts.google.com", "https://accounts.google.com"
        ):
            raise WorkloadIdentityDenied("Untrusted issuer")
        if claims.get("aud") != self.audience:
            raise WorkloadIdentityDenied("Incorrect audience")
        if claims.get("email_verified") is not True:
            raise WorkloadIdentityDenied("Unverified email")
        if claims.get("email") != self.bindings[agent_id]:
            raise WorkloadIdentityDenied("Agent workload mismatch")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise WorkloadIdentityDenied("Missing subject")
        return VerifiedCloudWorkload(
            agent_id, claims["email"], subject,
            claims["iss"], self.audience,
        )
