# StoreGuard — Governed Retail Resilience

StoreGuard is a research and executive-demonstration platform for governed AI-agent
operations, signed retail transactions and regional recovery on Google Cloud.

## Executive demonstration

The protected hosted dashboard demonstrates a fictional severe-weather exposure
scenario for 40 monitored stores and six exposed stores. Vault authenticates
agent workloads and manages short-lived credentials; StoreGuard authorizes and
audits each protected action. A **simulated client-side primary-path outage** is
followed by a **real signed order** to the recovery endpoint (`us-east4`) and an
independently verified Firestore receipt. The primary service is **not** actually
interrupted; this is not automated service failover or full DR.

The new Executive Experience v2 adds an evidence-derived six-stage story,
explicit Eastern timestamps, and an optional pop-out Execution Monitor showing
allowlisted event and correlated authorization/tool metadata. Vault token
revocation is not independently proved by the persisted executive event rows.

## Local verification

```bash
python3 -m pytest -q
```

The hosted Streamlit application lives in
`deployments/storeguard/hosted-executive/`. IAP protects the hosted application;
the operational demo should **not** be made public. The repository contains a
Google Cloud DR environment at `infrastructure/gcp/environments/dr-demo/`.

Review service configuration and identity/delegation scopes before launching
live demonstrations. Do not put private keys, secrets or bearer tokens in Git.
