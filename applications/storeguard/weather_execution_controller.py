"""Vault-governed execution of StoreGuard Weather Intelligence."""

import uuid

from applications.storeguard.weather_intelligence_agent import analyze_weather_threat
from identity.execution_gate import _event, _record
from identity.show_id import verify_agent_identity
from identity.vault_identity import managed_approle_session, VaultRevocationError
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT
from policy.weather_authorization import authorize_weather_assessment


class WeatherExecutionDenied(PermissionError):
    """Weather inference was not authorized."""


def execute_weather_intelligence(
    *,
    assessment,
    incident_id,
    allowed_store_ids,
    vault_addr,
    role_id,
    secret_id,
    model,
    client,
    db_path="data/storeguard_security_audit.sqlite3",
):
    """Authenticate, authorize, audit, and execute one weather inference."""
    run_id = str(uuid.uuid4())
    agent_name = WEATHER_RESPONSE_AGENT
    entity_id = None
    login_request_id = None
    audit_store_id = "MULTI_STORE"
    action = "assess_weather"
    started = False
    revoked = False

    def record(event_type, reason):
        event = _event(
            run_id, agent_name, audit_store_id, str(incident_id),
            event_type, reason, entity_id, login_request_id,
        )
        # Existing SRE event builder defaults to check_health.
        event["action"] = action
        _record(db_path, event)

    def on_revoked():
        nonlocal revoked
        revoked = True
        record("TOKEN_REVOKED", "Vault self-revocation acknowledged")

    try:
        with managed_approle_session(
            vault_addr=vault_addr,
            role_id=role_id,
            secret_id=secret_id,
            required_policy="storeguard-weather-readonly",
            on_token_revoked=on_revoked,
        ) as identity:
            entity_id = identity.entity_id
            login_request_id = identity.login_request_id

            verify_agent_identity(agent_name, identity)

            if not isinstance(incident_id, str) or (
                incident_id != assessment.threat_id
            ):
                raise WeatherExecutionDenied(
                    "Incident and threat identity do not match"
                )

            decision = authorize_weather_assessment(
                agent_name=agent_name,
                assessment=assessment,
                incident_id=incident_id,
                allowed_store_ids=allowed_store_ids,
            )
            if not decision.authorized:
                raise WeatherExecutionDenied(decision.reason)

            # Persist authorization before invoking the model.
            record(
                "AUTHORIZED",
                "Vault identity and all affected store scopes verified: "
                + ",".join(decision.store_ids),
            )
            record("STARTED", "Weather Intelligence inference started")
            started = True

            try:
                result = analyze_weather_threat(
                    assessment,
                    model=model,
                    client=client,
                )
            except Exception:
                record("INFERENCE_FAILED", "Weather inference raised an exception")
                raise

            record(
                "INFERENCE_COMPLETED",
                "Weather inference completed; Vault cleanup pending",
            )

        if not revoked:
            raise VaultRevocationError(
                "Vault token revocation was not confirmed"
            )

        record(
            "COMPLETED",
            "Weather inference and Vault token cleanup completed",
        )

        return {"run_id": run_id, "result": result}

    except VaultRevocationError:
        record("REVOCATION_FAILED", "Vault token revocation unconfirmed")
        raise

    except Exception as exc:
        if not started:
            record("DENIED", type(exc).__name__)
            raise WeatherExecutionDenied(
                "StoreGuard Weather Intelligence execution denied"
            ) from exc

        raise
