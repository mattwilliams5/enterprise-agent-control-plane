"""Failure-path tests for governed StoreGuard weather inference."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from applications.storeguard.threat_evaluation import ThreatAssessment
from applications.storeguard.weather_execution_controller import (
    WeatherExecutionDenied,
    execute_weather_intelligence,
)
from identity.vault_identity import VerifiedVaultIdentity, VaultRevocationError


STORES = (
    "SG-002", "SG-003", "SG-004",
    "SG-007", "SG-008", "SG-009",
)


@pytest.fixture
def assessment():
    return ThreatAssessment(
        threat_id="WEATHER-DEMO-001",
        evaluated_count=40,
        affected_store_ids=STORES,
        unaffected_store_ids=(),
    )


@contextmanager
def session(*, on_token_revoked=None, **kwargs):
    try:
        yield VerifiedVaultIdentity(
            entity_id="260976f6-efa7-1bfe-d002-d28e58640e71",
            policies=("storeguard-weather-readonly",),
            token_ttl=300,
            login_request_id="test-login",
        )
    finally:
        if on_token_revoked:
            on_token_revoked()


@contextmanager
def revocation_failure_session(**kwargs):
    yield VerifiedVaultIdentity(
        entity_id="260976f6-efa7-1bfe-d002-d28e58640e71",
        policies=("storeguard-weather-readonly",),
        token_ttl=300,
        login_request_id="test-login",
    )
    raise VaultRevocationError("Simulated revocation failure")


def execute(assessment, tmp_path):
    return execute_weather_intelligence(
        assessment=assessment,
        incident_id=assessment.threat_id,
        allowed_store_ids=frozenset(STORES),
        vault_addr="http://vault.test:8200",
        role_id="fake-role",
        secret_id="fake-secret",
        model="test-model",
        client=MagicMock(),
        db_path=str(tmp_path / "audit.sqlite3"),
    )


def test_authorization_audit_failure_blocks_inference(assessment, tmp_path):
    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller._record",
            side_effect=OSError("Simulated audit failure"),
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
        ) as inference,
    ):
        with pytest.raises(Exception):
            execute(assessment, tmp_path)

    inference.assert_not_called()


def test_inference_failure_propagates(assessment, tmp_path):
    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
            side_effect=RuntimeError("Simulated model failure"),
        ),
    ):
        with pytest.raises(RuntimeError, match="Simulated model failure"):
            execute(assessment, tmp_path)


def test_revocation_failure_propagates(assessment, tmp_path):
    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=revocation_failure_session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
            return_value="mock-report",
        ),
    ):
        with pytest.raises(VaultRevocationError):
            execute(assessment, tmp_path)
