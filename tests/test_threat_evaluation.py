"""Tests for geographic weather-threat evaluation."""

from math import inf, nan

import pytest

from applications.storeguard.controller import StoreGuardController
from applications.storeguard.state_machine import StoreState
from applications.storeguard.store_network import build_demo_network
from applications.storeguard.threat_evaluation import (
    WeatherThreat,
    evaluate_threat,
    haversine_km,
)


def test_identical_coordinates_have_zero_distance():
    assert haversine_km(35.4676, -97.5164, 35.4676, -97.5164) == 0


def test_known_distance_is_reasonable():
    # Approximate great-circle distance from equator 0° to 1° longitude.
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_threat_evaluates_all_40_stores():
    network = build_demo_network()
    threat = WeatherThreat("WX-001", 35.4676, -97.5164, 25)

    result = evaluate_threat(network, threat)

    assert result.threat_id == "WX-001"
    assert result.evaluated_count == 40
    assert len(result.affected_store_ids) == 10
    assert len(result.unaffected_store_ids) == 30
    assert set(result.affected_store_ids).isdisjoint(
        result.unaffected_store_ids
    )


def test_distant_threat_affects_no_stores():
    network = build_demo_network()
    threat = WeatherThreat("WX-002", 40.7128, -74.0060, 10)

    result = evaluate_threat(network, threat)

    assert result.affected_store_ids == ()
    assert len(result.unaffected_store_ids) == 40


def test_threat_evaluation_does_not_change_store_states():
    network = build_demo_network()
    controller = StoreGuardController()

    for store in network.all_stores():
        controller.register_store(store.store_id)

    before = {
        store_id: store.state
        for store_id, store in controller.stores.items()
    }

    evaluate_threat(
        network,
        WeatherThreat("WX-003", 35.4676, -97.5164, 25),
    )

    after = {
        store_id: store.state
        for store_id, store in controller.stores.items()
    }

    assert before == after
    assert all(state == StoreState.NORMAL for state in after.values())


@pytest.mark.parametrize(
    "latitude,longitude,radius",
    [
        (91, -97.5, 10),
        (35.4, 181, 10),
        (35.4, -97.5, 0),
        (35.4, -97.5, -1),
        (nan, -97.5, 10),
        (35.4, inf, 10),
        (35.4, -97.5, nan),
    ],
)
def test_invalid_threat_rejected(latitude, longitude, radius):
    with pytest.raises(ValueError):
        WeatherThreat("WX-BAD", latitude, longitude, radius)


def test_invalid_distance_coordinates_rejected():
    with pytest.raises(ValueError):
        haversine_km(95, 0, 0, 0)
