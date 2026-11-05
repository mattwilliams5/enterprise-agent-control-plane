# StoreGuard — Cloud Order Processing & Regional Recovery

**Repository:** `enterprise-agent-control-plane`  
**Development branch:** `feature/storeguard-executive-gui`  
**Status snapshot:** November 4, 2026 (last developer-verified results)

StoreGuard is an enterprise retail-resilience demonstration. Its order-processing subsystem models retail stores generating orders, retaining them locally during network disruption, and delivering them through region-aware application endpoints to a transactional Firestore ledger. The broader platform explores policy-governed, auditable agent operations.

> **Scope and safety:** This subsystem is a development/research demonstration, **not a production-ready disaster-recovery system**. Do not expose the existing development-key API publicly. Do not deploy or change paid cloud infrastructure without approval. Preserve uncommitted UI work; the Streamlit GUI is out of scope for the cloud-order batches.

## Verified status

| Area | Verified result | Important qualification |
|---|---|---|
| Automated suite | **241 passed** (Nov 4, 2026; 1.13 s) | Local regression tests; not a cloud-deployment qualification |
| Simulated retail workload | 40 stores generated 80 orders; store 1847 submitted live simulator orders | Not yet 40 separately authenticated cloud-connected stores |
| Local order API | FastAPI served on `127.0.0.1:8080`; observed HTTP 200, 409 and receipt lookups | Dev-key authentication only; server not necessarily running now |
| Firestore | `(default)` Native, Standard, `nam7`, pessimistic concurrency | Multi-region database shared by both proposed application regions |
| Live Firestore first-submission races | **2/2 passed**: `committed`+`duplicate` for equal payloads; `committed`+`conflict` for different amounts | Synthetic documents retained; not exhaustive load/fault testing |
| GCS Terraform state | `gs://storeguard-dr-demo-2026-tfstate/`, `US-CENTRAL1`; public access prevention, uniform access, versioning, 7-day soft delete | Bucket is regional, not cross-region failover of Terraform state |
| Cloud Run | No services listed in `us-central1` or `us-east4` at last check | No real Cloud Run regional failover demonstrated |
| Delivery reliability | Queue, leases, bounded retry, quarantine, regional preference/failback passed local tests | Batch 3 worker is opt-in; tests do not show it activated in a live simulator process |
| Store identity | 15 Ed25519 enrollment/signing/replay/rotation/revocation tests passed | Identity is not yet enforced by FastAPI or shared across Cloud Run instances |

## Architecture

```text
40 simulated store clients
       |
       v
Local SQLite durable order queue
       |
       v
Reliable delivery coordinator (leases, retry, quarantine)
       |
       v
Regional router + durable regional preference / controlled failback
       |                                  |
       v                                  v
Cloud Run primary (planned)          Cloud Run recovery (planned)
    us-central1                           us-east4
       \                                  /
        \                                /
          Shared Firestore transactional ledger
                      (nam7)
```

**Recovery boundary:** This topology supports *application-region recovery* once deployed and tested, not independent Firestore disaster recovery. Firestore point-in-time recovery was **disabled** at the last check. Cloud Run has not yet been deployed.

## Repository layout (relevant files)

```text
applications/storeguard/cloud_dr/
  order_api.py               # Local development FastAPI endpoint; shared dev-key auth
  order_ledger.py            # Firestore canonical order identity + key/receipt records
  order_queue.py             # Durable SQLite queue
  regional_router.py         # Primary/recovery HTTP routing
  queue_router_delivery.py   # Batch 2 coordinator
  delivery_reliability.py    # Batch 3 claim/lease/retry state
  reliable_delivery.py       # Batch 3 reliable processing
  regional_health.py         # Batch 3 persistent health/preference/failback
  health_aware_router.py     # Batch 3 health-aware regional routing
  store_identity.py          # Batch 5 Ed25519 identity primitives, local SQLite registry
scripts/
  verify_firestore_races.py  # Batch 4 opt-in real-Firestore race verification
tests/
  test_cloud_*.py            # Relevant local regression tests
```

## Prerequisites

- Python environment with project dependencies, including `pytest`, `fastapi`, `uvicorn`, `httpx`, `google-cloud-firestore`, `pydantic`, and `cryptography`.
- Google Cloud CLI and application-default credentials for live Firestore operations.
- Google Cloud project: `storeguard-dr-demo-2026` (only for authorized live-cloud exercises).
- Do not commit credentials, private keys, local SQLite databases, cached output, or staging folders.

## Local verification

From the repository root:

```bash
python3 -m pytest -q
```

The **last verified** outcome was `241 passed in 1.13s`. Your current result may differ as code evolves.

For focused security tests:

```bash
python3 -m pytest -q tests/test_cloud_store_identity.py
```

For the development API, configure local-only credentials outside Git and bind only to loopback:

```bash
export GOOGLE_CLOUD_PROJECT=storeguard-dr-demo-2026
export STOREGUARD_DEV_STORE_ID=1847
export STOREGUARD_DEV_API_KEY="$(cat .local/storeguard-dev-api-key)"
python3 -m uvicorn applications.storeguard.cloud_dr.order_api:app --host 127.0.0.1 --port 8080
```

**Never** reuse this development credential for publicly accessible endpoints. Do not treat `/health` returning `ok` as a complete readiness probe of Firestore or regional dependencies.

### Real Firestore concurrency test (opt-in)

This exercise **writes synthetic records to the existing project** and may incur usage charges. Obtain approval before repeating it:

```bash
export GOOGLE_CLOUD_PROJECT=storeguard-dr-demo-2026
python3 -m scripts.verify_firestore_races \
  --project storeguard-dr-demo-2026 \
  --ack-live-writes
```

Verified November 4, 2026: same-payload/different-key requests produced one `committed` and one `duplicate` response; different-amount/different-key requests produced one `committed` and one `conflict` response. Synthetic records were intentionally retained for inspection.

## Identity and governance

- **Store identity (prototype):** Batch 5 supports per-store Ed25519 keys, signed `POST /orders` request envelopes, key registration/revocation/rotation, and restart-persistent replay protection in **local SQLite**.
- **API enforcement (pending):** `order_api.py` still uses `STOREGUARD_DEV_API_KEY` and `STOREGUARD_DEV_STORE_ID`. The identity verifier must be integrated through a signed-only API boundary with no production fallback to the shared development key.
- **Cloud identity (pending):** Two Cloud Run regions need a trusted shared identity enrollment/revocation source and transactionally coordinated replay defense. Local SQLite is unsuitable for distributed enforcement.
- **Agent identity (pending):** SG-IDENTITY-001 requires fresh cryptographic identity verification on every agent run, current registration and revocation checks, scoped delegation/authorization, unique run ID, and auditable decisions. Store client authentication is **not** a substitute for agent authorization.
- **Service identity (planned):** Cloud Run should use appropriately scoped service accounts to reach Firestore.

## Delivery semantics and operating constraints

1. Persist an order before network submission; preserve logical order identity and the same idempotency key across retries.
2. Treat timeouts, 502/503/504, and lost acknowledgments as potentially committed transactions; only acknowledge confirmed receipts.
3. Quarantine durable authorization/conflict failures for investigation; never silently discard orders.
4. Do not run the legacy Batch 1/2 delivery loop in parallel with the Batch 3 reliable worker on the same SQLite queue.
5. Use **one** reliable worker per local queue until heartbeat, lease timing and multi-worker behavior are further validated.
6. Persistent recovery preference does not mean automatic primary failback. Independent probes and an explicit failback decision are required.
7. Historical orders written before canonical uniqueness existed need separate reconciliation.

## Known gaps and next milestones

1. Integrate cryptographic store authentication with FastAPI while preserving local development behavior; test signed request replay and negative cases at the endpoint.
2. Design a multi-region-safe identity registry and nonce store; define enrollment, key custody and recovery processes.
3. Enforce SG-IDENTITY-001 on real agent dispatch paths, with signed workload attestations and per-run auditing.
4. Validate the active simulator is actually using Batch 3 delivery processing; exercise crash recovery, delayed acknowledgments, timeouts, and recovery probes.
5. Reconcile historical pre-canonical orders; decide on Firestore PITR/backup and database-level DR.
6. With explicit security and billing approval, deploy private, cost-controlled Cloud Run services in `us-central1` and `us-east4`, then test **actual** regional failure and controlled failback before connecting all 40 stores.

**Cost target:** Less than USD $100/month, subject to actual billing verification. The current spend has not been measured here.

## Git hygiene

Use scoped staging and review every staged file before committing. In particular, exclude `.local/`, SQLite files, test output, archives, `*.bak`, private keys, secrets, and unrelated uncommitted Streamlit changes. Avoid `git add .`, `git clean`, or `git reset --hard` during this work.
