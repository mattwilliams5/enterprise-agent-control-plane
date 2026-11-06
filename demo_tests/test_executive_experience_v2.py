"""Tests for the new evidence-based narrative and pop-out monitor."""
from datetime import datetime, timezone
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

src = (Path(__file__).resolve().parents[1] / 'deployments/storeguard/hosted-executive'
       / 'ui/storeguard/cloud_story.py')
spec = spec_from_file_location('storeguard_v2_story', src)
module = module_from_spec(spec)
spec.loader.exec_module(module)
event_rows, monitor_url = module.event_rows, module.monitor_url
action_audit_rows = module.action_audit_rows
narrative, timestamp_pair = module.narrative, module.timestamp_pair


def sample():
    summary = {
        'verified': True,
        'exposed': ['SG-002', 'SG-003'],
        'agents': [{'agent_id': 'Weather', 'authorization_run_id': 'auth-1',
                    'action_gate_run_id': 'gate-1', 'action_run_id': 'action-1'}],
        'receipt': {'status': 'recovery_transaction_verified',
                    'order': {'region': 'recovery', 'outcome': 'acknowledged',
                              'receipt_id': 'receipt-1', 'attempts': [
                                  {'region': 'primary', 'error': 'SIMULATED_CLIENT_SIDE_OUTAGE'},
                                  {'region': 'recovery', 'status_code': 200}]}}
    }
    events = [
        {'event_type': 'DR_RECEIPT_VERIFIED', 'timestamp': '2026-11-06T23:11:00Z',
         'detail': {'secret': 'DO_NOT_RENDER', 'receipt_id': 'receipt-1'}},
        {'event_type': 'THREAT_ASSESSED', 'timestamp': '2026-11-06T23:10:00Z',
         'detail': {'untrusted': 'DO_NOT_RENDER'}},
        {'event_type': 'AGENT_COMPLETED', 'timestamp': '2026-11-06T23:10:30Z',
         'detail': {'agent_id': 'Weather', 'action': 'assess_weather', 'token': 'DO_NOT_RENDER'}}]
    return summary, events


def test_eastern_label_with_est():
    assert '6:10:00 PM EST' in timestamp_pair('2026-11-06T23:10:00Z')[0]


def test_dst_summer_label():
    assert 'EDT' in timestamp_pair(datetime(2026, 7, 6, 23, 10, tzinfo=timezone.utc))[0]


def test_no_timezone_guess():
    assert timestamp_pair('2026-11-06T23:10:00')[0] == 'Timezone unknown'


def test_allowlist_and_sort_and_no_secrets():
    _, events = sample()
    rows = event_rows(events)
    assert [row['Event'] for row in rows] == [
        'Weather exposure assessed', 'Governed agent action completed', 'Recovery receipt verified']
    assert 'DO_NOT_RENDER' not in str(rows)


def test_story_requires_verified_order():
    summary, events = sample()
    assert narrative(summary, events)['verified']
    summary['receipt']['order']['attempts'][1]['status_code'] = 503
    assert not narrative(summary, events)['verified']


def test_missing_agent_auth_does_not_count():
    summary, events = sample()
    del summary['agents'][0]['authorization_run_id']
    assert narrative(summary, events)['actions'] == 0


def test_popout_same_origin_and_validated():
    url = monitor_url('https://example.run.app/cloud_tornado?x=y', 'run_123')
    assert url == 'https://example.run.app/execution-monitor?run=run_123'
    try:
        monitor_url('https://example.run.app/', '../bad')
        assert False
    except ValueError:
        pass


def test_audit_rows_match_current_run_only():
    summary, _ = sample()
    tools = [{'action_run_id': 'action-1', 'agent_id': 'Weather',
              'event_type': 'TOOL_ALLOWED', 'timestamp': '2026-11-06T23:10:32Z',
              'secret': 'DO_NOT_RENDER'},
             {'action_run_id': 'other-run', 'event_type': 'TOOL_ALLOWED'}]
    decisions = [{'run_id': 'auth-1', 'action': 'assess_weather',
                  'recorded_at': '2026-11-06T23:10:25Z', 'token': 'DO_NOT_RENDER'},
                 {'run_id': 'auth-other', 'action': 'assess_weather'}]
    rows = action_audit_rows(summary, tools, decisions)
    assert len(rows) == 2
    assert rows[0]['Evidence'] == 'Authorization record'
    assert 'DO_NOT_RENDER' not in str(rows)


def test_agent_identifiers_are_safe():
    _, events = sample()
    events[-1]['detail']['authorization_run_id'] = 'auth-1'
    events[-1]['detail']['action_gate_run_id'] = 'gate-1'
    events[-1]['detail']['action_run_id'] = 'action-1'
    events[-1]['detail']['agent_id'] = 'TOKEN=secret-value'
    rows = event_rows(events)
    agent = next(row for row in rows if row['Event'] == 'Governed agent action completed')
    assert agent['Agent'] == ''
    assert agent['Authorization ID'] == 'auth-1'
