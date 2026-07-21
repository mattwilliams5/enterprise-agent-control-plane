from datetime import UTC, datetime, timedelta
from uuid import uuid4

def issue_temporary_credentials(
    agent_name: str,
    resource: str,
    ttl_seconds: int = 300,
    ) -> dict:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)

    credential = {
        "lease_id": str(uuid4()),
        "agent": agent_name,
        "resource": resource,
        "token": f"temporary-token-{uuid4()}",
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
    }

    return credential

      