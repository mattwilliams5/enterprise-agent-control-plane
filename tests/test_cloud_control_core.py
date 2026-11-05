import pytest
from applications.storeguard.cloud_control.core import new_exercise, transition, TransitionDenied, PHASES

def test_all_transitions():
    state = new_exercise()
    for action in ('start', 'route_fault', 'recover', 'request_review', 'complete_checks'):
        state = transition(state, action, 'test-actor')
    assert state['phase'] == 5
    assert state['version'] == 5
    assert len(state['events']) == 5
    assert all(e['mode'] == 'SIMULATED' for e in state['events'])

def test_cannot_skip_steps():
    with pytest.raises(TransitionDenied):
        transition(new_exercise(), 'recover', 'test')

def test_cannot_repeat_action():
    state = transition(new_exercise(), 'start', 'test')
    with pytest.raises(TransitionDenied):
        transition(state, 'start', 'test')

def test_no_secrets_or_live_claims():
    state = transition(new_exercise(), 'start', 'test')
    assert state['simulation'] is True
    assert 'token' not in str(state).lower()
    assert 'private_key' not in str(state).lower()
