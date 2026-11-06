from applications.storeguard.store_network import build_demo_network
from applications.storeguard.threat_evaluation import WeatherThreat
from applications.storeguard.multi_agent_planner import (
    plan_weather_response,
    SRE_AGENT,
)
from policy.storeguard_actions import WEATHER_RESPONSE_AGENT


def _threat(radius):
    return WeatherThreat(
        threat_id="WX-TEST-001",
        latitude=35.4676,
        longitude=-97.5164,
        radius_km=radius,
    )


def test_network_has_40_stores():
    assert len(build_demo_network()) == 40


def test_planner_creates_two_items_per_affected_store():
    plan = plan_weather_response(build_demo_network(), _threat(20))
    assert len(plan.work_items) == 2 * len(
        plan.assessment.affected_store_ids
    )


def test_planner_assigns_distinct_agent_roles():
    plan = plan_weather_response(build_demo_network(), _threat(20))
    assert {item.agent_name for item in plan.work_items} == {
        WEATHER_RESPONSE_AGENT,
        SRE_AGENT,
    }


def test_planner_does_not_schedule_unaffected_stores():
    plan = plan_weather_response(build_demo_network(), _threat(20))
    affected = set(plan.assessment.affected_store_ids)
    assert all(item.store_id in affected for item in plan.work_items)


def test_all_work_remains_planned():
    plan = plan_weather_response(build_demo_network(), _threat(20))
    assert all(item.status == "PLANNED" for item in plan.work_items)


def test_plan_is_deterministic():
    network = build_demo_network()
    threat = _threat(20)
    assert plan_weather_response(network, threat) == plan_weather_response(
        network, threat
    )
