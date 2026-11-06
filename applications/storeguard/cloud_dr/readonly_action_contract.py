"""Shared, dependency-light deny-by-default read-only action vocabulary."""

class ToolDenied(PermissionError):
    pass

READ_ONLY_TOOL_ACTIONS = frozenset({
    "assess_weather", "recommend_protection", "investigate_store"
})
