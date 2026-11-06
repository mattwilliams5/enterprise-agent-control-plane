"""StoreGuard action vocabulary and deny-by-default policy."""

from enum import Enum


class StoreGuardAction(str, Enum):
    ASSESS_WEATHER = "assess_weather"
    RECOMMEND_PROTECTION = "recommend_protection"
    ENTER_PROTECTED = "enter_protected"
    ENTER_MAINTENANCE = "enter_maintenance"
    ENTER_RECOVERY = "enter_recovery"
    RETURN_NORMAL = "return_normal"


WEATHER_RESPONSE_AGENT = "storeguard-weather-response-agent"


READ_ONLY_ACTIONS = frozenset({
    StoreGuardAction.ASSESS_WEATHER,
    StoreGuardAction.RECOMMEND_PROTECTION,
})


STATE_CHANGING_ACTIONS = frozenset({
    StoreGuardAction.ENTER_PROTECTED,
    StoreGuardAction.ENTER_MAINTENANCE,
    StoreGuardAction.ENTER_RECOVERY,
    StoreGuardAction.RETURN_NORMAL,
})


def is_weather_action_allowed(agent_name: str, action: str) -> bool:
    """Check static action eligibility; not execution authorization.

    This function does not verify identity, registration, delegation,
    incident scope, or human approval. Those checks must occur
    independently before any operational execution.
    """
    if agent_name != WEATHER_RESPONSE_AGENT:
        return False

    try:
        requested_action = StoreGuardAction(action)
    except (ValueError, TypeError):
        return False

    return requested_action in READ_ONLY_ACTIONS
