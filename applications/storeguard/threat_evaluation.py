"""Deterministic geographic threat evaluation for StoreGuard."""

from dataclasses import dataclass
from math import asin, cos, isfinite, radians, sin, sqrt

from applications.storeguard.store_network import StoreNetwork


EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance in kilometers."""
    coordinates = (lat1, lon1, lat2, lon2)

    if not all(isfinite(value) for value in coordinates):
        raise ValueError("Coordinates must be finite")

    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("Invalid latitude")

    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("Invalid longitude")

    lat1, lon1, lat2, lon2 = map(radians, coordinates)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, a)))


@dataclass(frozen=True)
class WeatherThreat:
    threat_id: str
    latitude: float
    longitude: float
    radius_km: float

    def __post_init__(self):
        if not self.threat_id.strip():
            raise ValueError("Threat ID cannot be empty")

        if not all(isfinite(value) for value in (
            self.latitude, self.longitude, self.radius_km
        )):
            raise ValueError("Threat coordinates and radius must be finite")

        if not -90 <= self.latitude <= 90:
            raise ValueError("Invalid threat latitude")

        if not -180 <= self.longitude <= 180:
            raise ValueError("Invalid threat longitude")

        if self.radius_km <= 0:
            raise ValueError("Threat radius must be positive")


@dataclass(frozen=True)
class ThreatAssessment:
    threat_id: str
    evaluated_count: int
    affected_store_ids: tuple[str, ...]
    unaffected_store_ids: tuple[str, ...]


def evaluate_threat(
    network: StoreNetwork,
    threat: WeatherThreat,
) -> ThreatAssessment:
    """Evaluate store exposure without changing operational state."""
    affected = []
    unaffected = []

    for store in network.all_stores():
        distance = haversine_km(
            store.latitude,
            store.longitude,
            threat.latitude,
            threat.longitude,
        )

        if distance <= threat.radius_km:
            affected.append(store.store_id)
        else:
            unaffected.append(store.store_id)

    return ThreatAssessment(
        threat_id=threat.threat_id,
        evaluated_count=len(affected) + len(unaffected),
        affected_store_ids=tuple(affected),
        unaffected_store_ids=tuple(unaffected),
    )
