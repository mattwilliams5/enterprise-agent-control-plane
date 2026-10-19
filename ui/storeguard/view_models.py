"""Presentation-only models for the StoreGuard dashboard.

These models intentionally contain no policy, risk, agent, Vault, Terraform,
or state-transition logic. The application/control plane will eventually feed
these values to the GUI.
"""
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum


class StoreMode(str, Enum):
    NORMAL = "NORMAL"
    PROTECTED = "PROTECTED"
    MAINTENANCE = "MAINTENANCE"
    RECOVERY = "RECOVERY"


class Health(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    WAITING = "WAITING"


@dataclass(frozen=True)
class StoreView:
    store_id: str
    city: str
    state: str
    cloud: str
    mode: StoreMode = StoreMode.NORMAL
    health: Health = Health.HEALTHY
    weather_risk: str = "LOW"


@dataclass(frozen=True)
class AgentEventView:
    event_type: str
    message: str
    status: str = "complete"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).strftime("%H:%M:%S"))


@dataclass(frozen=True)
class IncidentView:
    incident_id: str
    title: str
    severity: str
    affected_store_ids: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class IdentityView:
    provider: str = "IBM Verify"
    human_status: str = "Not connected"
    agent_name: str = "store-resiliency-agent"
    vault_status: str = "Not connected"
    credential_status: str = "None"
