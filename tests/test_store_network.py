"""Tests for the StoreGuard geographic store registry."""

import pytest

from applications.storeguard.store_network import (
    StoreLocation,
    StoreNetwork,
    build_demo_network,
)


def test_demo_network_contains_40_stores():
    network = build_demo_network()

    assert len(network) == 40
    assert len(network.all_stores()) == 40


def test_each_region_contains_10_stores():
    network = build_demo_network()

    for region in ("Oklahoma", "Kansas", "Texas", "Missouri"):
        assert len(network.by_region(region)) == 10


def test_store_ids_are_unique():
    network = build_demo_network()
    ids = [store.store_id for store in network.all_stores()]

    assert len(ids) == len(set(ids))
    assert ids[0] == "SG-001"
    assert ids[-1] == "SG-040"


def test_duplicate_store_registration_rejected():
    network = StoreNetwork()
    store = StoreLocation("SG-001", "Test Store", "Oklahoma", 35.4, -97.5)

    network.register(store)

    with pytest.raises(ValueError, match="Duplicate store"):
        network.register(store)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (91.0, -97.5),
        (-91.0, -97.5),
        (35.4, 181.0),
        (35.4, -181.0),
    ],
)
def test_invalid_coordinates_rejected(latitude, longitude):
    with pytest.raises(ValueError):
        StoreLocation(
            "SG-001",
            "Test Store",
            "Oklahoma",
            latitude,
            longitude,
        )


def test_store_lookup_and_immutable_collection():
    network = build_demo_network()

    store = network.get("SG-001")

    assert store is not None
    assert store.region == "Oklahoma"
    assert network.get("SG-999") is None
    assert isinstance(network.all_stores(), tuple)
