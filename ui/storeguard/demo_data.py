"""Deterministic presentation fixtures for the StoreGuard GUI.

This is intentionally *not* the StoreGuard state machine or risk engine. It
exists only so the visual layer can be developed before those components are
implemented together.
"""
from ui.storeguard.view_models import (
    AgentEventView,
    Health,
    IdentityView,
    IncidentView,
    StoreMode,
    StoreView,
)

CLOUDS = ("AWS", "Azure", "GCP", "On-Prem")
CITIES = (
    ("Oklahoma City", "OK"), ("Tulsa", "OK"), ("Wichita", "KS"),
    ("Topeka", "KS"), ("Dallas", "TX"), ("Fort Worth", "TX"),
    ("Amarillo", "TX"), ("Lubbock", "TX"), ("Omaha", "NE"),
    ("Lincoln", "NE"),
)


def build_demo_stores() -> list[StoreView]:
    stores = []
    for index in range(100):
        city, state = CITIES[index % len(CITIES)]
        stores.append(
            StoreView(
                store_id=str(1800 + index),
                city=city,
                state=state,
                cloud=CLOUDS[index % len(CLOUDS)],
            )
        )
    return stores


def tornado_fixture(stores: list[StoreView]) -> tuple[list[StoreView], IncidentView, list[AgentEventView]]:
    targets = {"1847", "1851", "1863"}
    updated = [
        StoreView(
            store_id=s.store_id,
            city=s.city,
            state=s.state,
            cloud=s.cloud,
            mode=StoreMode.PROTECTED if s.store_id in targets else s.mode,
            health=s.health,
            weather_risk="HIGH" if s.store_id in targets else s.weather_risk,
        )
        for s in stores
    ]
    incident = IncidentView(
        incident_id="WX-2026-001",
        title="Tornado warning — Oklahoma/Kansas corridor",
        severity="HIGH",
        affected_store_ids=tuple(sorted(targets)),
        status="PROTECTED MODE",
    )
    events = [
        AgentEventView("WEATHER_ALERT_RECEIVED", "Severe weather alert received"),
        AgentEventView("STORE_RISK_DETECTED", "3 stores intersect the demonstration risk area"),
        AgentEventView("PROTECTED_MODE_REQUESTED", "Protected mode requested for affected stores", "working"),
    ]
    return updated, incident, events


def demo_identity() -> IdentityView:
    return IdentityView()
