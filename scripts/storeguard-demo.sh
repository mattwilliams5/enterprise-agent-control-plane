#!/usr/bin/env bash
# StoreGuard SA front door. No deployment, IAM, or secrets changes.
set -euo pipefail
PROJECT="${STOREGUARD_PROJECT:-storeguard-dr-demo-2026}"
REGION="${STOREGUARD_REGION:-us-central1}"
JOB="${STOREGUARD_DEMO_JOB:-storeguard-one-trigger-demo}"
cmd="${1:-help}"

usage() {
  cat <<EOF
StoreGuard demo — Solutions Architect commands
  ./scripts/storeguard-demo.sh check   Check CLI, access, services, and demo job
  ./scripts/storeguard-demo.sh run     Execute the preconfigured one-trigger job ONCE
  ./scripts/storeguard-demo.sh logs    Show recent demo job logs
  ./scripts/storeguard-demo.sh help    Show help

Project: $PROJECT  Region: $REGION  Job: $JOB
Requires one-time administrator bootstrap (IAM, approved delegations,
Secret Manager mounts, source build, and deployed job).
EOF
}

need_gcloud() {
  command -v gcloud >/dev/null || { echo 'STOP: Install Google Cloud CLI first.' >&2; exit 2; }
  gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . || {
    echo 'STOP: No active gcloud account. Run: gcloud auth login' >&2; exit 2;
  }
}

job_exists() {
  gcloud run jobs describe "$JOB" --project="$PROJECT" --region="$REGION" --format='value(metadata.name)' >/dev/null 2>&1
}

case "$cmd" in
  help|-h|--help) usage ;;
  check)
    need_gcloud
    echo "Checking $PROJECT / $REGION (read-only)..."
    for item in 'us-central1 storeguard-orders-primary' 'us-east4 storeguard-orders-recovery'; do
      read -r region service <<<"$item"
      ready=$(gcloud run services describe "$service" --project="$PROJECT" --region="$region" --format='value(status.conditions[0].status)' 2>/dev/null || true)
      [[ "$ready" == True ]] || { echo "STOP: $service not ready or access denied ($region)."; exit 3; }
      echo "PASS: $service ready ($region)"
    done
    if ! job_exists; then
      echo "STOP: $JOB is not deployed or you cannot see it."
      echo "The operator must first complete SA_QUICKSTART.md > One-time setup."
      exit 3
    fi
    echo "PASS: Demo job exists ($JOB)"
    echo 'NOTE: Existence does not prove secrets, delegation expiry, or invocation permission.'
    echo 'PASS: Basic preflight completed'
    ;;
  run)
    need_gcloud
    if ! job_exists; then
      echo "STOP: Demo job $JOB not found or access denied; no execution started." >&2
      exit 3
    fi
    echo 'A real synthetic order may be written to the Firestore operational ledger.'
    echo 'Storm exposure and primary client outage are simulated, not a real outage.'
    echo 'Human approval and store recovery are NOT performed.'
    read -r -p 'Execute the demo once? Type RUN: ' acknowledgement
    [[ "$acknowledgement" == RUN ]] || { echo 'Cancelled; no execution started.'; exit 0; }
    gcloud run jobs execute "$JOB" --project="$PROJECT" --region="$REGION" --wait
    echo 'Use ./scripts/storeguard-demo.sh logs to inspect evidence and PASS markers.'
    ;;
  logs)
    need_gcloud
    gcloud logging read \
      "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$JOB\"" \
      --project="$PROJECT" --freshness=2h --limit=60 \
      --format='table(timestamp,severity,textPayload)'
    ;;
  *) echo "Unknown command: $cmd" >&2; usage; exit 2 ;;
esac
