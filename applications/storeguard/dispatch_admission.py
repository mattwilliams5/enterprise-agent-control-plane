"""Fail-closed admission for planned StoreGuard agent work.

Admission is not execution authorization.
"""

from dataclasses import dataclass

from applications.storeguard.multi_agent_planner import AgentWorkItem
from policy.agent_capabilities import is_capability_declared
from registry.registry import get_agent_record


@dataclass(frozen=True)
class DispatchDecision:
    work_item: AgentWorkItem
    status: str
    reason: str


def admit_work_item(
    item: AgentWorkItem,
    *,
    incident_id: str,
    allowed_store_ids: frozenset[str],
) -> DispatchDecision:
    """Check static eligibility before governed execution."""

    def deny(reason: str) -> DispatchDecision:
        return DispatchDecision(item, "DENIED", reason)

    if not isinstance(item, AgentWorkItem):
        raise TypeError("Expected AgentWorkItem")

    if item.status != "PLANNED":
        return deny("Work item is not in PLANNED state")

    if not item.threat_id or not item.store_id or not incident_id:
        return deny("Missing threat, store, or incident scope")

    if item.store_id not in allowed_store_ids:
        return deny("Store outside dispatcher scope")

    if not is_capability_declared(item.agent_name, item.action):
        return deny("Agent capability not declared")

    record = get_agent_record(item.agent_name)

    if record is None:
        return deny("Agent is not registered")

    if not record.approved or record.status != "active":
        return deny("Agent is not approved and active")

    if not record.vault_entity_id:
        return deny("Agent lacks trusted Vault identity binding")

    return DispatchDecision(
        item,
        "READY_FOR_GOVERNED_EXECUTION",
        "Eligible for independent execution-time verification",
    )
