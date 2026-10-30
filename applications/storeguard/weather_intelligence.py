"""Weather intelligence presentation adapter. No live forecast or provider connection."""
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class WeatherIntelligence:
    source: Literal["simulated", "live"]
    event_type: str
    headline: str
    severity: str
    affected_store_ids: tuple[str, ...]
    incident_id: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    provider: str | None = None
    location: str | None = None

    def __post_init__(self):
        if self.source == "live" and not (self.provider and self.issued_at):
            raise ValueError("Live weather requires a provider and issuance timestamp")


def from_demo_incident(incident) -> WeatherIntelligence | None:
    """Adapt an existing scenario fixture; do not invent meteorological measurements."""
    if incident is None:
        return None
    return WeatherIntelligence(
        source="simulated", event_type="Tornado / severe storm",
        headline=str(incident.title), severity=str(incident.severity),
        affected_store_ids=tuple(str(s) for s in incident.affected_store_ids),
        incident_id=str(incident.incident_id),
    )


def weather_view(event: WeatherIntelligence | None, *, compact: bool = False) -> dict:
    if event is None:
        return {"headline": "No active simulated weather event", "detail": "Weather API not connected", "badge": "Simulation ready", "compact": compact}
    return {
        "headline": event.headline,
        "detail": f"{event.event_type} · Severity: {event.severity} · {len(event.affected_store_ids)} stores exposed",
        "badge": "SIMULATED WEATHER" if event.source == "simulated" else f"LIVE · {event.provider}",
        "compact": compact,
    }
