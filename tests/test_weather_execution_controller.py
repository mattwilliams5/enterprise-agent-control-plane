"""Security tests for governed Weather Intelligence execution."""

from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

from applications.storeguard.threat_evaluation import ThreatAssessment
from applications.storeguard.weather_execution_controller import (
    execute_weather_intelligence,
    WeatherExecutionDenied,
)
from identity.vault_identity import VerifiedVaultIdentity


STORES = (
    "SG-002", "SG-003", "SG-004",
    "SG-007", "SG-008", "SG-009",
)

ENTITY_ID = "260976f6-efa7-1bfe-d002-d28e58640e71"


@pytest.fixture
def assessment():
    return ThreatAssessment(
        threat_id="WEATHER-DEMO-001",
        evaluated_count=40,
        affected_store_ids=STORES,
        unaffected_store_ids=(),
    )


@contextmanager
def fake_session(*, entity_id=ENTITY_ID, on_token_revoked=None, **kwargs):
    assert kwargs["required_policy"] == "storeguard-weather-readonly"

    try:
        yield VerifiedVaultIdentity(
            entity_id=entity_id,
            policies=("storeguard-weather-readonly",),
            token_ttl=300,
            login_request_id="test-login",
        )
    finally:
        if on_token_revoked:
            on_token_revoked()


def run_controller(assessment, allowed_store_ids, tmp_path):
    return execute_weather_intelligence(
        assessment=assessment,
        incident_id=assessment.threat_id,
        allowed_store_ids=allowed_store_ids,
        vault_addr="http://vault.test:8200",
        role_id="fake-role",
        secret_id="fake-secret",
        model="test-model",
        client=MagicMock(),
        db_path=str(tmp_path / "audit.sqlite3"),
    )


def test_authorized_weather_inference(assessment, tmp_path):
    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=fake_session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
            return_value="mock-weather-report",
        ) as inference,
    ):
        result = run_controller(
            assessment,
            frozenset(STORES),
            tmp_path,
        )

    assert result["result"] == "mock-weather-report"
    inference.assert_called_once()


def test_unauthorized_store_blocks_openai(assessment, tmp_path):
    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=fake_session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
        ) as inference,
    ):
        with pytest.raises(WeatherExecutionDenied):
            run_controller(
                assessment,
                frozenset(STORES[:-1]),
                tmp_path,
            )

    inference.assert_not_called()


def test_wrong_vault_identity_blocks_openai(assessment, tmp_path):
    def wrong_identity_session(**kwargs):
        return fake_session(
            entity_id="wrong-vault-entity",
            **kwargs,
        )

    with (
        patch(
            "applications.storeguard.weather_execution_controller.managed_approle_session",
            side_effect=wrong_identity_session,
        ),
        patch(
            "applications.storeguard.weather_execution_controller.analyze_weather_threat",
        ) as inference,
    ):
        with pytest.raises(WeatherExecutionDenied):
            run_controller(
                assessment,
                frozenset(STORES),
                tmp_path,
            )

    inference.assert_not_called()
