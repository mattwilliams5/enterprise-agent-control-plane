#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v gcloud >/dev/null 2>&1; then
  echo 'STOP: gcloud CLI is not installed.' >&2; exit 1
fi
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  echo 'STOP: Local Google ADC is missing. Run: gcloud auth application-default login' >&2; exit 1
fi
python3 - <<'PY'
try:
    import streamlit, google.cloud.firestore, google.auth
except ImportError as exc:
    raise SystemExit(f'STOP: Python dependency missing: {exc}. Install Streamlit and google-cloud-firestore in your repo venv.')
PY
export STOREGUARD_CLOUD_MODE=1
export STOREGUARD_GUI_LOCAL_OPERATOR=1
export STOREGUARD_GUI_BIND_ADDRESS=127.0.0.1
export GOOGLE_CLOUD_PROJECT=storeguard-dr-demo-2026
export STOREGUARD_EVIDENCE_DATABASE=storeguard-executive-evidence
export STOREGUARD_PRIMARY_CLOUD_URL=https://storeguard-orders-primary-2zr27trg4a-uc.a.run.app
export STOREGUARD_RECOVERY_CLOUD_URL=https://storeguard-orders-recovery-2zr27trg4a-uk.a.run.app
printf 'Launching private local StoreGuard operator UI at http://127.0.0.1:8501\n'
exec python3 -m streamlit run ui/storeguard/app.py \
  --server.address=127.0.0.1 --server.port=8501 --server.headless=true
