#!/usr/bin/env bash
set -euo pipefail

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export STOREGUARD_VAULT_ADDR="$VAULT_ADDR"

TOKEN_FILE="/tmp/storeguard-provisioner-token.json"
ROLE="storeguard-investigator"
POLICY="storeguard-provisioner"

echo "=== StoreGuard Secure Startup ==="

# 1. Check Vault is reachable and unsealed.
vault status -format=json | python3 -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("initialized") or d.get("sealed"):
    sys.exit("Vault is not initialized or is sealed")
print("PASS: Vault is initialized and unsealed")
'

# 2. Confirm the provisioner policy exists.
vault policy read "$POLICY" >/dev/null
echo "PASS: Provisioner policy exists"

# 3. Verify the investigator AppRole exists.
vault read "auth/approle/role/$ROLE" >/dev/null
echo "PASS: Investigator AppRole exists"

# 4. Create a restricted token for this demo session.
umask 077
tmp_file="$(mktemp "${TOKEN_FILE}.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT

vault token create \
    -policy="$POLICY" \
    -ttl=30m \
    -explicit-max-ttl=30m \
    -orphan \
    -format=json > "$tmp_file"

chmod 600 "$tmp_file"

# 5. Validate token and its expected policy.
TOKEN_FILE="$tmp_file" python3 - <<'PY'
import json
import os
from pathlib import Path

import requests

token = json.loads(
    Path(os.environ["TOKEN_FILE"]).read_text()
)["auth"]["client_token"]

response = requests.get(
    os.environ["VAULT_ADDR"].rstrip("/")
    + "/v1/auth/token/lookup-self",
    headers={"X-Vault-Token": token},
    timeout=8,
)
response.raise_for_status()

data = response.json()["data"]
policies = set(data.get("policies", []))

if "root" in policies:
    raise SystemExit("FAIL: Root token is not permitted")

if "storeguard-provisioner" not in policies:
    raise SystemExit("FAIL: Provisioner policy missing")

if data.get("ttl", 0) <= 0:
    raise SystemExit("FAIL: Invalid token lifetime")

print("PASS: Restricted provisioner token verified")
print("Remaining TTL:", data["ttl"], "seconds")
PY

# 6. Atomically install the credential.
mv -f "$tmp_file" "$TOKEN_FILE"
echo "PASS: Provisioner credential installed"

echo ""
echo "Starting StoreGuard..."
exec python3 -m streamlit run ui/storeguard/app.py
