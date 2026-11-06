"""Strict, deterministic, cloud-safe DR rehearsal state machine.

No signed orders, agent credentials, or infrastructure mutation occurs here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

PHASES = (
    'NORMAL', 'PROTECTED', 'PRIMARY_ROUTE_FAULT',
    'RECOVERY_ROUTED', 'AWAITING_OPERATOR_REVIEW', 'NORMAL_RESTORED',
)
ACTIONS = {
    'start': (0, 1),
    'route_fault': (1, 2),
    'recover': (2, 3),
    'request_review': (3, 4),
    'complete_checks': (4, 5),
}

class TransitionDenied(ValueError):
    pass

def new_exercise() -> dict[str, Any]:
    return {'id': uuid4().hex, 'phase': 0, 'version': 0, 'simulation': True,
            'events': [], 'created_at': datetime.now(timezone.utc).isoformat()}

def transition(state: dict[str, Any], action: str, actor: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise TransitionDenied('Unknown command')
    old, new = ACTIONS[action]
    if state['phase'] != old:
        raise TransitionDenied(f'{action} not allowed in {PHASES[state["phase"]]}')
    result = dict(state)
    result['phase'] = new
    result['version'] = state['version'] + 1
    result['events'] = [*state['events'], {
        'action': action, 'actor': actor, 'phase': PHASES[new],
        'version': result['version'],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mode': 'SIMULATED',
    }]
    return result
