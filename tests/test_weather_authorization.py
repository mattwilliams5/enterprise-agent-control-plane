"""Security tests for StoreGuard multi-store weather authorization."""

import pytest

from applications.storeguard.threat_evaluation import ThreatAssessment
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT
from policy.weather_authorization import authorize_weather_assessment


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
        unaffected_store_ids=tuple(
            f"SG-{i:03d}"
            for i in range(1, 41)
            if f"SG-{i:03d}" not in STORES
        ),
    )


def decide(assessment, **overrides):
    arguments = {
        "agent_name": WEATHER_RESPONSE_AGENT,
        "assessment": assessment,
        "incident_id": "INC-WEATHER-001",
        "allowed_store_ids": frozenset(STORES),
    }
    arguments.update(overrides)
    return authorize_weather_assessment(**arguments)


def test_all_six_stores_authorized(assessment):
    decision = decide(assessment)
    assert decision.authorized
    assert decision.store_ids == STORES


@pytest.mark.parametrize(
    "allowed",
    [
        frozenset(STORES[:-1]),
        frozenset(),
    ],
)
def test_incomplete_store_scope_denied(assessment, allowed):
    assert not decide(
        assessment,
        allowed_store_ids=allowed,
    ).authorized


def test_unknown_agent_denied(assessment):
    assert not decide(
        assessment,
        agent_name="unknown-weather-agent",
    ).authorized


def test_missing_incident_denied(assessment):
    assert not decide(
        assessment,
        incident_id="",
    ).authorized


def test_duplicate_store_denied(assessment):
    duplicate = ThreatAssessment(
        threat_id=assessment.threat_id,
        evaluated_count=40,
        affected_store_ids=STORES + (STORES[0],),
        unaffected_store_ids=(),
    )
    assert not decide(duplicate).authorized


def test_empty_affected_scope_denied():
    empty = ThreatAssessment(
        threat_id="WEATHER-DEMO-001",
        evaluated_count=40,
        affected_store_ids=(),
        unaffected_store_ids=(),
    )
    assert not decide(empty).authorized
