from types import SimpleNamespace
import pytest
from applications.storeguard.weather_intelligence import WeatherIntelligence, from_demo_incident, weather_view


def test_no_incident():
    assert from_demo_incident(None) is None
    assert "not connected" in weather_view(None)["detail"]


def test_fixture_mapping():
    incident = SimpleNamespace(title="Tornado approaching", severity="high", incident_id="WX-1", affected_store_ids=[1847, 1848, 1849])
    weather = from_demo_incident(incident)
    assert weather.source == "simulated"
    assert weather.affected_store_ids == ("1847", "1848", "1849")
    assert weather_view(weather)["badge"] == "SIMULATED WEATHER"


def test_compact_is_presentation_only():
    weather = from_demo_incident(SimpleNamespace(title="Storm", severity="high", incident_id="WX", affected_store_ids=[1]))
    assert weather_view(weather, compact=True)["compact"] is True
    assert weather_view(weather, compact=False)["headline"] == weather_view(weather, compact=True)["headline"]


def test_live_requires_provenance():
    with pytest.raises(ValueError):
        WeatherIntelligence(source="live", event_type="Tornado", headline="Warning", severity="high", affected_store_ids=())
