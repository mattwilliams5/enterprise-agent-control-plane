# StoreGuard One-Trigger Cloud Job

This directory contains the build definition for the existing Vault-governed Cloud Run job.

Build from Git-tracked application and policy sources.
The Vault CA certificate is public trust material, not the Vault private key.
Runtime credentials must be injected through approved identity and secret mechanisms.
Do not commit store signing keys, Vault tokens, or OpenAI API credentials.
Do not deploy directly from this directory without assembling the complete Git-tracked build context.
