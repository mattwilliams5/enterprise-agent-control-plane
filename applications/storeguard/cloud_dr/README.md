# StoreGuard | Cloud Resilience & Governed Agents

> **Status:** Development demonstration · **Branch:** `feature/storeguard-executive-gui` · **Last verified:** November 5, 2026
>
> **Test baseline:** **296 passing** · **Cloud:** Firestore in `nam7`; no confirmed Cloud Run deployment in either target region · **GUI:** Existing Streamlit UI unchanged by these cloud batches

StoreGuard demonstrates how a network of retail stores can keep orders durable during disruption, restore application connectivity through regional routing, and make agent decisions traceable to verified identities and policy. The system is **not yet a production DR solution**.

## At a glance

| Proven | Built and locally tested | Not yet proven |
|---|---|---|
| 40 independently signed store clients reached a **local** FastAPI server; 40 orders and 40 receipts independently verified in **real Firestore** | Durable queue retry/leases, regional health and controlled failback, shared Firestore identity/replay components, Vault agent adapters | Dual-region Cloud Run failover, real cross-region replay/revocation, live Vault agent enforcement at every protected action, independent database recovery |
| Live Firestore same-order concurrency races passed for the two tested scenarios | 296 automated tests pass | Production security and availability requirements |

**Cloud project:** `storeguard-dr-demo-2026`
**Firestore:** Native `(default)`, Standard edition, multi-region `nam7`
**App regions planned:** `us-central1` (primary), `us-east4` (recovery)
**Terraform state:** `gs://storeguard-dr-demo-2026-tfstate/` (`us-central1`)

## Architecture

```text
40 independently enrolled stores (Ed25519 signing keys)
          │
          ▼
Durable local SQLite order queues ──► retries / lease-based delivery
          │
          ▼
Signed HTTP request verification ──► store identity + revocation + replay checks
          │
          ▼
Regional router + health tracking / controlled failback
          ├──────────────────────────┐
          ▼                          ▼
 Cloud Run us-central1        Cloud Run us-east4
       (planned)                   (planned)
          └────────────┬─────────────┘
                       ▼
       Shared Firestore transaction ledger (`nam7`)
       canonical order ─ idempotency key ─ receipt

Separate governance path (partially integrated):
Vault workload authentication → agent registry → delegation/scope policy
→ auditable run decision → protected action checks
```

**Important:** The successful 40-store cloud test used FastAPI on **localhost** with Firestore as the remote ledger. It was **not** an application hosted on Cloud Run. The regional diagram above is a target architecture, not a deployed topology. Firestore multi-region availability is not independent database disaster recovery.

## Quick start (safe, local)

From the repository root, using the project's installed Python environment:

```bash
python3 -m pytest -q
```

Last reported result: **296 passed in 2.40s**. Tests alone do not establish live GCP or Vault readiness.

### Local signed API and offline HTTP exercise

Private identities must already be enrolled under `.local/storeguard-identity-demo/`; **never commit or sync that directory**. Check the enrollment instructions and offline smoke runbook in the applicable batch integration guide before re-enrolling or creating a new queue.

**Terminal A** (offline ledger; no Firestore writes):

```bash
export STOREGUARD_IDENTITY_DB="$PWD/.local/storeguard-identity-demo/trusted_stores.sqlite3"
mkdir -p .local/storeguard-http-demo
export STOREGUARD_OFFLINE_LEDGER_DB="$PWD/.local/storeguard-http-demo/orders.sqlite3"
python3 -m uvicorn applications.storeguard.cloud_dr.offline_signed_api:app \
  --host 127.0.0.1 --port 8081
```

**Terminal B** (read-only health check):

```bash
curl -fsS http://127.0.0.1:8081/health
```

The previously completed demonstration delivered **40 queued orders over real localhost HTTP** and left **0 pending orders**. Do not reseed or replace an existing SQLite queue without reviewing its state.

### Signed API backed by real Firestore — *opt-in only*

The `signed_order_api:app` process can use real Firestore on `127.0.0.1:8082`. **Starting the server is not an invitation to repeat a live write run.** Live tests must use the explicit operator-approval flag in the Batch 5D/5E runbook; writes consume cloud quota, can incur charges, and intentionally retain synthetic records.

Verified live run: `1f96d9c0bd60` — **40 canonical orders, 40 receipts, 40 distinct stores**, plus 40 successful fresh signed idempotent retries and 40 rejected replays reported by the client. The Firestore counts were checked independently. Two earlier first-submission race scenarios also passed (matching orders: committed/duplicate; conflicting amounts: committed/conflict).

## Code map

| Area | Key modules |
|---|---|
| Transaction ledger | `order_ledger.py`, `order_api.py` (local dev-key API only) |
| Durability / delivery | `order_queue.py`, `queue_router_delivery.py`, `delivery_reliability.py`, `reliable_delivery.py`, `signed_queue_delivery.py` |
| Regional routing | `regional_router.py`, `regional_health.py`, `health_aware_router.py` |
| Signed stores / APIs | `store_identity.py`, `signed_order_api.py`, `offline_signed_api.py` |
| Shared cloud identity prototype | `shared_store_identity.py`, `cloud_signed_order_api.py` |
| Agent governance prototype | `agent_execution_gate.py`, `vault_agent_adapters.py`; existing `identity/`, `registry/`, `policy/` |
| Operator scripts | `scripts/enroll_store_fleet.py`, `scripts/smoke_signed_fleet.py`, `scripts/smoke_signed_http.py`, `scripts/run_signed_queue.py`, `scripts/verify_firestore_races.py` |
| Verification | `tests/test_cloud_*.py` |

All filenames above are relative to `applications/storeguard/cloud_dr/` unless another path is shown.

## Trust and safety boundaries

- **Independent store identity:** Each store uses an Ed25519 key pair. A verified signature—not a caller-supplied `X-Store-ID` alone—must establish store identity in the signed API.
- **Development API is local-only:** `order_api.py` still supports a single local development key. **Never publish that endpoint with the shared key**, even behind a public URL.
- **Replay defense:** Local SQLite verification works for local tests. Firestore-backed shared trust/nonce handling has unit tests but still requires **live concurrent, cross-process, cross-region and revocation validation**, including nonce retention/cleanup policy.
- **Agent requirements (SG-IDENTITY-001):** Every run needs fresh cryptographic workload identity verification, current registration/revocation and delegation/scope checks, a unique run ID, and an auditable decision. Every protected tool action must recheck authorization/revocation; never reuse prior-run authorization.
- **Vault:** Existing managed AppRole session and adapters have tests. They do **not** yet prove end-to-end live Vault token lifecycle, independent delegation authority, cloud-wide audit durability or protected-tool enforcement.
- **Delivery:** Keep stable logical order IDs and idempotency keys through retries; an HTTP timeout can occur *after* commit. Only mark acknowledged after a verified receipt. Do not run legacy and reliable delivery workers together on one queue. Multi-worker lease/heartbeat correctness is not yet proven.
- **GUI freeze:** Do not edit the existing Streamlit executive GUI without explicit approval. Preserve all uncommitted work.
- **Infrastructure:** No billable deployment or publicly accessible API without authorization. Budget target: **under $100/month**; actual spend must be checked in Google Cloud Billing.

## Remaining milestones

1. **6A validation:** Exercise shared Firestore trust, replay, key rotation and revocation with real cross-process contention; enforce a retention policy and validate failure behavior.
2. **6B/6C Vault enforcement:** Wire trusted delegation, active registration, per-run policy, durable audit and protected action authorization to the real agent runtime; test against Vault.
3. **Cloud deployment readiness:** Review least-privilege IAM, private Cloud Run invocation, Terraform plan, scaling/concurrency limits, logging and budget alerts. Require explicit deployment approval.
4. **Real application failover:** Deploy private Cloud Run services in both regions; verify timeout/lost-ack recovery, regional loss and operator-controlled failback with 40 stores.
5. **Executive end-to-end demo:** Integrate weather/incident response, governed agents, store protection and transaction recovery with the existing GUI **only after requirements and GUI approval**.

**Separate follow-ups:** Reconcile historical pre-canonical orders; choose Firestore PITR/backup and an independent database recovery strategy. Firestore PITR was **disabled** at the last resource inspection.

## Git hygiene and checkpoints

The cloud subsystem was previously committed at `c08f1e9`; newer batches 5B–6C may be uncommitted locally. Stage **specific files**, review `git diff --cached`, and run `git diff --cached --check` before committing. Never stage `.local/`, key material, SQLite DBs, ZIP archives, backups or unrelated GUI files. Avoid `git add .`, `git clean`, and destructive resets.

> **Definition of done for the full demo:** Actual regional failover has been exercised, every protected agent action is identity-verified and authorized at execution time, audit evidence is durable, business outcomes are visible in the approved executive GUI, and recovery can be repeated from a documented runbook.
