"""Read-only verification against StoreGuard's local Vault audit device.

Development source: Docker stdout. No tokens, SecretIDs, or audit
accessor HMACs are returned to the UI.
"""
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class VaultAuditResult:
    status: str
    detail: str
    login_request_id: str | None = None
    revoke_request_id: str | None = None


def verify_vault_audit(login_request_id, entity_id, *, container="storeguard-vault"):
    if not login_request_id or not entity_id:
        return VaultAuditResult("pending", "Execution has no recorded Vault login correlation.")

    try:
        result = subprocess.run(
            ["docker", "logs", "--since", "24h", container],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return VaultAuditResult("unavailable", "Vault audit source is unavailable.")

    if result.returncode != 0:
        return VaultAuditResult("unavailable", "Cannot read Vault server audit records.")

    records = []
    for line in result.stdout.splitlines() + result.stderr.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if item.get("type") not in ("request", "response"):
            continue
        records.append(item)

    def request(record):
        return record.get("request") or {}

    def auth(record):
        return record.get("auth") or {}

    def matching(path, request_id, kind):
        return [
            r for r in records
            if r.get("type") == kind
            and request(r).get("path") == path
            and request(r).get("id") == request_id
            and request(r).get("operation") == "update"
        ]

    login_requests = matching("auth/approle/login", login_request_id, "request")
    login_responses = matching("auth/approle/login", login_request_id, "response")

    if len(login_requests) != 1 or len(login_responses) != 1:
        return VaultAuditResult("partial", "Vault login request/response pair not uniquely verified.", login_request_id)

    login = login_responses[0]
    if login.get("error") or login_requests[0].get("error"):
        return VaultAuditResult("partial", "Vault login audit reports an error.", login_request_id)

    if auth(login).get("entity_id") != entity_id:
        return VaultAuditResult("partial", "Vault login entity does not match StoreGuard.", login_request_id)

    accessor = auth(login).get("accessor")
    if not accessor:
        return VaultAuditResult("partial", "Vault login audit accessor is missing.", login_request_id)

    revokes = [
        r for r in records
        if request(r).get("path") == "auth/token/revoke-self"
        and request(r).get("operation") == "update"
        and auth(r).get("accessor") == accessor
    ]

    revoke_ids = {request(r).get("id") for r in revokes}
    revoke_ids.discard(None)

    if len(revoke_ids) != 1:
        return VaultAuditResult("partial", "Unique Vault revocation not established.", login_request_id)

    revoke_id = next(iter(revoke_ids))
    revoke_requests = matching("auth/token/revoke-self", revoke_id, "request")
    revoke_responses = matching("auth/token/revoke-self", revoke_id, "response")

    if len(revoke_requests) != 1 or len(revoke_responses) != 1:
        return VaultAuditResult("partial", "Vault revocation request/response pair is incomplete.", login_request_id)

    pair = revoke_requests + revoke_responses
    if any(r.get("error") for r in pair):
        return VaultAuditResult("partial", "Vault revocation audit reports an error.", login_request_id)

    if any(auth(r).get("accessor") != accessor for r in pair):
        return VaultAuditResult("partial", "Vault revocation accessor mismatch.", login_request_id)

    if any(auth(r).get("entity_id") != entity_id for r in pair):
        return VaultAuditResult("partial", "Vault revocation entity mismatch.", login_request_id)

    if not (
        login_requests[0].get("time", "")
        <= login.get("time", "")
        <= revoke_requests[0].get("time", "")
        <= revoke_responses[0].get("time", "")
    ):
        return VaultAuditResult("partial", "Vault audit event ordering is inconsistent.", login_request_id)

    return VaultAuditResult(
        "verified",
        "AppRole authentication and token revocation independently correlated.",
        login_request_id,
        revoke_id,
    )
