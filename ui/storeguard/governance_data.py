"""Read-only executive presentation adapter. No authentication claims are inferred."""
import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from registry.registry import AGENT_REGISTRY


def registry_rows():
    rows = []
    for key, record in sorted(AGENT_REGISTRY.items()):
        manifest = {
            "agent_id": key,
            "name": record.name,
            "owner": record.owner,
            "environment": record.environment,
            "purpose": record.purpose,
            "risk_level": record.risk_level,
            "approved": record.approved,
            "status": record.status,
            "vault_entity_id": record.vault_entity_id,
        }
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        rows.append({"manifest": manifest, "fingerprint": hashlib.sha256(canonical.encode()).hexdigest()})
    return rows


def vault_health():
    """Unauthenticated local health probe; does not prove agent authentication."""
    addr = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200").rstrip("/")
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not (addr.startswith("http://127.0.0.1:") or addr.startswith("http://localhost:") or addr.startswith("https://")):
        return {"status": "Unknown", "detail": "Unsupported Vault address for dashboard health probe", "checked": checked, "address": "Not displayed"}
    try:
        try:
            response = urlopen(addr + "/v1/sys/health", timeout=2)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.status
            info = json.loads(response.read().decode("utf-8"))
        if status == 200 and info.get("initialized") and not info.get("sealed"):
            label, detail = "Connected", "Vault reports initialized and unsealed"
        elif status in (429, 472, 473, 501, 503):
            label, detail = "Unavailable", f"Vault health HTTP {status}"
        else:
            label, detail = "Unknown", f"Unexpected Vault health HTTP {status}"
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        label, detail = "Unavailable", type(exc).__name__
    return {"status": label, "detail": detail, "checked": checked, "address": addr}
