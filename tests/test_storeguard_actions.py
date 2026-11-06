"""Tests for StoreGuard's deny-by-default action policy."""

import pytest

from policy.storeguard_actions import (
    StoreGuardAction,
    WEATHER_RESPONSE_AGENT,
    READ_ONLY_ACTIONS,
    STATE_CHANGING_ACTIONS,
    is_weather_action_allowed,
)


@pytest.mark.parametrize("action", sorted(READ_ONLY_ACTIONS))
def test_weather_agent_has_read_only_eligibility(action):
    assert is_weather_action_allowed(
        WEATHER_RESPONSE_AGENT, action
    )


@pytest.mark.parametrize("action", sorted(STATE_CHANGING_ACTIONS))
def test_weather_agent_cannot_change_store_states(action):
    assert not is_weather_action_allowed(
        WEATHER_RESPONSE_AGENT, action
    )


@pytest.mark.parametrize(
    "agent_name",
    [
        "sre-troubleshooting-agent",
        "unknown-agent",
        "",
    ],
)
def test_other_agents_have_no_weather_permissions(agent_name):
    for action in StoreGuardAction:
        assert not is_weather_action_allowed(agent_name, action)


@pytest.mark.parametrize(
    "action",
    [
        "delete_store",
        "approve_recovery",
        "override_policy",
        "",
        None,
    ],
)
def test_unknown_actions_are_denied(action):
    assert not is_weather_action_allowed(
        WEATHER_RESPONSE_AGENT, action
    )


def test_action_categories_do_not_overlap():
    assert READ_ONLY_ACTIONS.isdisjoint(STATE_CHANGING_ACTIONS)


def test_every_defined_action_is_classified():
    assert (
        READ_ONLY_ACTIONS | STATE_CHANGING_ACTIONS
    ) == frozenset(StoreGuardAction)
