#!/usr/bin/env bash
set -euo pipefail

# Local development Vault uses HTTP.
# Set this before the first Vault CLI command.
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export STOREGUARD_VAULT_ADDR="$VAULT_ADDR"

PROJECT="storeguard-dr-demo-2026"
PRIMARY_PORT=8080
RECOVERY_PORT=9092
GUI_PORT=8501

mkdir -p .local/cloud-demo
PIDS=()

cleanup() {
  echo
  echo "Stopping demo-owned Cloud Run proxies..."
  for pid in "${PIDS[@]-}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

echo "=== StoreGuard Demo Preflight ==="

for tool in gcloud vault curl python3 streamlit lsof; do
  command -v "$tool" >/dev/null || {
    echo "Missing dependency: $tool"
    exit 1
  }
done

test "$(gcloud config get-value project 2>/dev/null)" = "$PROJECT" || {
  echo "Incorrect active Google Cloud project"
  exit 1
}

vault status -format=json | python3 -c '
import json,sys
v=json.load(sys.stdin)
assert v.get("initialized") and not v.get("sealed")
print("PASS: Local Vault initialized and unsealed")
'

for port in "$PRIMARY_PORT" "$RECOVERY_PORT" "$GUI_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN |
     grep -q LISTEN; then
    echo "Port $port is already occupied. Stop its service first."
    exit 1
  fi
done

echo "Starting primary Cloud Run proxy..."
gcloud run services proxy storeguard-orders-primary \
  --project="$PROJECT" \
  --region=us-central1 \
  --port="$PRIMARY_PORT" \
  > .local/cloud-demo/primary-proxy.log 2>&1 &
PIDS+=("$!")

echo "Starting recovery Cloud Run proxy..."
gcloud run services proxy storeguard-orders-recovery \
  --project="$PROJECT" \
  --region=us-east4 \
  --port="$RECOVERY_PORT" \
  > .local/cloud-demo/recovery-proxy.log 2>&1 &
PIDS+=("$!")

check_health() {
  local port="$1"
  for attempt in {1..30}; do
    if curl -fsS --max-time 5 \
      "http://127.0.0.1:${port}/health" |
      python3 -c '
import json,sys
d=json.load(sys.stdin)
assert d["status"]=="ok"
assert d["authentication"]=="shared-signed-only"
assert d["backend"]=="firestore"
' 2>/dev/null; then
      echo "PASS: Cloud Run proxy on port $port"
      return 0
    fi
    sleep 1
  done
  echo "FAILED: Cloud Run proxy on port $port"
  return 1
}

check_health "$PRIMARY_PORT"
check_health "$RECOVERY_PORT"

echo "=== Launching existing StoreGuard GUI ==="
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export STOREGUARD_VAULT_ADDR="$VAULT_ADDR"
export STOREGUARD_PRIMARY_URL="http://127.0.0.1:8080"
export STOREGUARD_RECOVERY_URL="http://127.0.0.1:9092"

streamlit run ui/storeguard/app.py \
  --server.port "$GUI_PORT" \
  --server.address 127.0.0.1
