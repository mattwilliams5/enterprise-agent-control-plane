"""Deterministic fingerprint of StoreGuard's registered agent metadata."""

import hashlib
import json
from dataclasses import asdict

from registry.registry import get_agent_record


def registration_fingerprint(agent_name: str) -> str:
    record = get_agent_record(agent_name)
    if record is None:
        raise ValueError("Agent is not registered")

    canonical = json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()
