# StoreGuard — Solutions Architect Quickstart

**Goal:** clone the repo, run a few commands, and demonstrate a simulated tornado scenario with *real governed cloud agents* and a *real signed recovery-region transaction*. The tornado and primary-client outage are **simulated**. The primary Cloud Run service is **not** shut down. Neither human approval nor store-level recovery is automated or claimed.

## The SA experience (after one-time cloud setup)

**Before the demo:** Your administrator must provide repository access, `gcloud` access to the approved demo project, and a *deployed, configured* Cloud Run Job named `storeguard-one-trigger-demo` in `us-central1`. Do not copy secret keys or create fresh store identities.

```bash
# 1. Clone the approved repo once the integration has been merged to main.
git clone <YOUR_APPROVED_REPO_URL>
cd enterprise-agent-control-plane

# 2. Sign in using your assigned Google Cloud account.
gcloud auth login

# 3. Check the existing cloud environment (no changes).
./scripts/storeguard-demo.sh check

# 4. Run the ONE-trigger demo. Type RUN at the safety prompt.
./scripts/storeguard-demo.sh run

# 5. Review results.
./scripts/storeguard-demo.sh logs
```

**Success** is a completed Cloud Run Job with `PASS: One-trigger StoreGuard demo completed`, `PASS: Fresh Vault governed weather and SRE actions`, `PASS: Recovery service acknowledged actual signed order`, and `PASS: Shared Firestore receipt independently verified`. The log includes a demo run ID and receipt ID. The job also creates auditable records in `storeguard_demo_events`, and the agent decisions/tool events in their existing collections. Verify the records in the *named* evidence database and the receipt in the operational `(default)` database before claiming a live proof.

To show the existing GUI, open the approved **private** `storeguard-executive` Cloud Run service through your organization-authorized access flow. The new one-button UI is **not yet implemented**; these shell commands are the interim one-trigger front door. Do not describe static sample cards as live evidence.

## What to say during the demo

> “We inject a fictional Oklahoma tornado event across a 40-store network. StoreGuard identifies six geographically exposed stores. For SG-002, the Weather Intelligence and SRE agents each demonstrate fresh Vault workload verification, policy authorization, and an audit trail. We simulate a primary *client-side* outage without disabling the real primary service. A signed synthetic order is actually processed by our private recovery-region Cloud Run service, and StoreGuard independently verifies its Firestore receipt. Operational store recovery and human approval are intentionally not simulated as real actions.”

## Quick troubleshooting

| Symptom | Meaning / next action |
|---|---|
| `STOP: ... job not deployed` | Administrator must deploy and configure the one-trigger job. Cloning does not create cloud infrastructure. |
| `403` Cloud Run invocation | SA may not have `run.jobs.run`, or runtime principal may lack scoped `run.invoker` on both private order services. Ask administrator; **do not make services public**. |
| `verification_or_policy_error` | Vault GCP identity/registration/delegation problem; check denial audit. Never disable authorization to make demo pass. |
| Missing/expired delegation | Administrator must review and renew both separate SG-002 delegations (24-hour expiry). |
| Missing OpenAI credential | Administrator must mount a valid Secret Manager secret on the runtime; do not paste it into shell history. |
| Store key missing | Administrator must provide the already-enrolled SG-002 private signing key as a Secret Manager **file**, and its registered key ID. Never mint a replacement silently. |
| `DR_NOT_VERIFIED` | Recovery transaction was not confirmed; do not claim failover. Inspect job log and receipt validation. |
| No `PASS` markers | Stop, inspect the last execution and evidence; don't rerun blindly, because each run creates a new real test order. |

## One-time setup (platform/security owner only)

This setup is **not** part of the SA presentation. It must be completed and verified once per approved environment; delegations have to be renewed as they expire.

1. Merge/review the backend integration and `scripts/storeguard-demo.sh` into the approved Git repository. The ZIP is a patch, not a standalone repo. Preserve unrelated uncommitted work, backups, and GUI files.
2. Create a reproducible, pinned Cloud Run Job image from the reviewed repository with the required Python packages (`openai`, `pydantic`, `google-cloud-firestore`, `google-auth`, `requests`, `httpx`, `cryptography`, etc.), Vault TLS CA certificate, and `python -m applications.storeguard.cloud_dr.run_one_trigger_demo` as its entrypoint. Do **not** reuse or overwrite the proven SRE or Vault auth-probe jobs.
3. Deploy the **private** `storeguard-one-trigger-demo` job under `storeguard-agent-runtime@storeguard-dr-demo-2026.iam.gserviceaccount.com` with the existing private Vault VPC/subnet and egress sufficient for GCP APIs/OpenAI and private Cloud Run service endpoints. Bind its fixed `GOOGLE_CLOUD_PROJECT` and `STOREGUARD_DEMO_ARMED=SIMULATED_PRIMARY_OUTAGE_REAL_ORDER` settings for an approved demo only.
4. Grant that agent service account `roles/run.invoker` **on the two order services only** (`storeguard-orders-primary` in `us-central1`; `storeguard-orders-recovery` in `us-east4`). Grant the minimum read access necessary to `storeguard_orders` in the default Firestore database (for receipt verification). Do **not** grant broad project-wide Firestore write access. Maintain existing named evidence DB grants only as necessary; segregate administrative docs and runtime writes before any production claim.
5. Mount via Secret Manager (not environment plaintext) (a) `OPENAI_API_KEY` and (b) the **existing enrolled** SG-002 private key as a base64 encoded 32-byte Ed25519 file; provide its matching `STOREGUARD_STORE_KEY_ID`. Ensure the runtime principal can read only those secrets.
6. Check actual Vault GCP role/policy, live TLS CA path, and current Firestore registrations/delegations for `storeguard-weather-response-agent` and `sre-troubleshooting-agent`. Renew approved 24-hour delegations, never bypass expiry, and preserve two fresh checks per protected action. Both logical agents currently share one workload principal: **demo limitation**, not production isolation.
7. Confirm both private order APIs use the same Firestore default-ledger data, registered store public key, and replay protections; test the live recovery path with exactly one synthetic order and independently verify its receipt.
8. Give SAs **run-and-read** permissions for this one job and the private GUI via existing IAM; do not hand them service-account keys, Vault root tokens, or broad Firestore database rights. Enforce the agreed budget, monitoring and cost controls.
9. Run focused mock tests first: `python3 -m pytest -q demo_tests/test_live_signed_failover.py demo_tests/test_one_trigger_demo.py`. Perform one approved live pilot before labeling the environment **SA ready**.

**Current reality:** The supplied integration has passed seven mock tests, but the one-trigger Cloud Run Job **has not yet been deployed/live-validated**, and the proposed GUI button is not yet in place. Until the operator setup is complete, the five SA shell commands above are a **target workflow**, not a claim of turnkey readiness.
