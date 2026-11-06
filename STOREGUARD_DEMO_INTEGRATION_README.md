# StoreGuard — One-trigger DR demonstration integration

**Delivered:** Backend source integration plus focused mock tests. **NOT yet deployed or verified against live GCP**. Existing Streamlit GUI is **unchanged** pending user review/approval.

## What this package adds

- `live_signed_failover.py`: Google OIDC identity token (target service audience) plus independently Ed25519-signed exact HTTP body on each attempt. Preserves order IDs and idempotency; verifies matching receipt. Denies 401/403/409/422 without failover; only switches regions after transport errors/502/503/504 or explicit client-side fault injection. No public service access.
- `one_trigger_demo.py`: One call assesses the fictional tornado, independently runs the **already governed** weather and SRE actions for **SG-002 only**, then sends an authenticated synthetic order to the recovery region and persists evidence. Stops if governance fails. Other five stores are exposure-only until separately registered and delegated.
- `run_one_trigger_demo.py`: Cloud Run Job entry point, guardrailed to an explicitly armed, trusted runtime. Uses actual `OpenAI()` weather inference and Vault GCP identity checks. Reads a pre-enrolled SG-002 private Ed25519 key from a mounted secret, never from the browser. Independently checks the returned receipt in the **operational** default Firestore ledger and writes demo evidence to the separate named evidence database.
- `readonly_action_contract.py`: Dependency-light shared tool action vocabulary, avoiding eager import of legacy Vault AppRole/hvac into the GCP-governed runner. `cloud_governed_runner.py` and `protected_readonly_tools.py` both import the exact same class/allowlist.

## Apply to the repository (on Mac)

Review the 7 source files in this archive first. From the **repository root**, extract the provided zip **after** confirming the paths won't overwrite unexpected local modifications. Files `cloud_governed_runner.py` and `protected_readonly_tools.py` are modified, and `readonly_action_contract.py` plus 3 new backend modules are added. Do not replace the entire repository; the ZIP only includes these files, tests, and this README.

Run only the focused tests: `python3 -m pytest -q demo_tests/test_live_signed_failover.py demo_tests/test_one_trigger_demo.py`. Seven tests passed in the isolated supplied source environment. Other project tests and live cloud behavior have not been rerun here.

## Deployment prerequisites — do not bypass

1. Run on the **existing agent-runtime service account** with Vault GCP login and fresh Firestore delegation checks. This is currently the only principal bound to the Vault `storeguard-agent` role; using the executive-runtime SA without changing Vault binding will fail.
2. To call private orders services, this agent-runtime service account must receive `roles/run.invoker` **only on** `storeguard-orders-primary` in `us-central1` and `storeguard-orders-recovery` in `us-east4`. Existing executive-runtime access should remain unchanged. This is a scoped IAM change and requires operator authorization.
3. It must read `storeguard_orders` on the `(default)` Firestore database to independently verify receipts. This is distinct from its existing access to the named `storeguard-executive-evidence` database. Grant the narrowest feasible read-only database access; do **not** add blanket roles/datastore.user to the project.
4. The already-enrolled `SG-002` Ed25519 **private** key must be injected from Secret Manager as a mounted file of base64-encoded raw 32-byte bytes. Set `STOREGUARD_STORE_KEY_FILE` to the secret mount and `STOREGUARD_STORE_KEY_ID` to its actual already-registered key ID. Never create a new key silently, and never place key bytes in the ZIP/repository.
5. Inject `OPENAI_API_KEY` through Secret Manager, not `--set-env-vars` with plaintext values. Runtime needs Secret Manager access only to required secrets.
6. Cloud Run Job needs outbound HTTPS to OpenAI, Google Cloud APIs and the private Cloud Run service hosts, and private network access/TLS to Vault. Retain existing VPC and CA certificate configuration. Enforce cost budget.
7. Configure `GOOGLE_CLOUD_PROJECT=storeguard-dr-demo-2026` and `STOREGUARD_DEMO_ARMED=SIMULATED_PRIMARY_OUTAGE_REAL_ORDER` only for this controlled, one-off demonstration. The entry point refuses normal/local execution.
8. Verify the two regional API revisions share the same Firestore store public keys, nonce replay store, idempotency ledger and response contract. They currently point to `(default)` Firestore in code, but a live cross-region write has not been proven here.
9. Existing SG-002 weather and SRE delegations expire 24h after creation. Renew through an authorized administrative process before the run if expired. Do not bypass expiry/revocation checks.
10. Isolate source build for the new job; do not overwrite the proven `storeguard-sre-investigation` or the `storeguard-vault-auth-probe` job. Existing agent runtime Firestore write privileges over admin registration/delegation must be separated before production use.

## Proof criteria

A successful run prints `PASS` and emits create-only events in `storeguard_demo_events`: THREAT_ASSESSED, AGENT_COMPLETED twice, and DR_RECEIPT_VERIFIED. Two fresh authorization gates per agent are enforced by the existing `CloudGovernedReadOnlyRunner`, and the tool audits are stored by its current Firestore adapter. The order verifier separately reads the `(default)` `storeguard_orders` collection to confirm receipt and matching signed transaction identity.

**What this does NOT prove:** A real tornado, actual GCP region outage, human approval, six-store governed execution, store-level recovery/state transitions, failback, independent database failover, or production DR readiness. Fault injection bypasses only the primary *client request* to safely demonstrate the live recovery service. Simulation control API remains unchanged.

## Executive GUI (not modified)

Suggested approved change after backend GCP verification: add a single `Run simulated tornado DR demo` control; display 40 total / 6 simulated exposed / 1 governed store; live stage evidence from the named Firestore `storeguard_demo_events`; Vault identity/authorization/action IDs from existing collections; authenticated recovery region order receipt from live backend; and explicit human-approval hold. Visually separate simulated tornado/primary-client fault from real signed transaction and actual Cloud Run services. Do not imply one checkbox grants human approval.
