from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3
import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import AgentIntent, AgentDenied
from applications.storeguard.cloud_dr.vault_agent_adapters import SqliteDecisionAudit
from applications.storeguard.cloud_dr.protected_readonly_tools import (
    ProtectedReadOnlyRunner, SqliteToolAudit, ToolDenied,
)

AGENT = 'storeguard-weather-response-agent'
ENTITY = '260976f6-efa7-1bfe-d002-d28e58640e71'


def intent(**changes):
    params = dict(agent_id=AGENT, incident_id='INC1', store_id='1800',
                  action='assess_weather', delegation_id='DEL1')
    params.update(changes)
    return AgentIntent(**params)


class SessionHarness:
    def __init__(self):
        self.logins = 0
        self.revoke_ok = True

    @contextmanager
    def login(self, **kwargs):
        self.logins += 1
        assert kwargs['secret_id'] == f'fresh-{self.logins}'
        yield SimpleNamespace(entity_id=ENTITY, token_ttl=30,
                              login_request_id=f'vault-{self.logins}')
        if not self.revoke_ok:
            raise RuntimeError('revocation failed')


def build(tmp_path, *, delegation=lambda **kw: True, scope=lambda **kw: True,
          handler=None, harness=None, audit=None):
    harness = harness or SessionHarness()
    audit = audit or SqliteToolAudit(tmp_path/'tool.sqlite3')
    handler = handler or (lambda i: {'status':'assessed'})
    runner = ProtectedReadOnlyRunner(
        audit=audit, decision_audit=SqliteDecisionAudit(tmp_path/'decisions.sqlite3'),
        delegation_check=delegation, scope_check=scope,
        handlers={'assess_weather': handler}, session_factory=harness.login)
    return runner, harness, audit


def test_two_tool_calls_get_two_fresh_logins_and_four_decisions(tmp_path):
    runner, harness, _ = build(tmp_path)
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        a = runner.execute(intent=intent(), vault_addr='http://localhost',role_id='r',
                           secret_id_supplier=lambda: f'fresh-{harness.logins+1}')
        b = runner.execute(intent=intent(), vault_addr='http://localhost',role_id='r',
                           secret_id_supplier=lambda: f'fresh-{harness.logins+1}')
    assert a['action_run_id'] != b['action_run_id']
    assert harness.logins == 2
    with sqlite3.connect(tmp_path/'decisions.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM gate_decisions').fetchone()[0] == 4


def test_state_changes_denied_without_login_or_tool_run(tmp_path):
    runner, harness, _ = build(tmp_path)
    with pytest.raises(ToolDenied):
        runner.execute(intent=intent(action='enter_protected'), vault_addr='x',role_id='r',
                       secret_id_supplier=lambda:'fresh-1')
    assert harness.logins == 0


@pytest.mark.parametrize('field', ['delegation', 'scope'])
def test_denied_scope_blocks_handler(tmp_path, field):
    called=[]
    runner, harness, _ = build(tmp_path, handler=lambda i: called.append(i),
        delegation=(lambda **kw: field != 'delegation'),
        scope=(lambda **kw: field != 'scope'))
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(AgentDenied):
            runner.execute(intent=intent(), vault_addr='x',role_id='r',
                           secret_id_supplier=lambda:'fresh-1')
    assert called == []


def test_second_check_revocation_prevents_execution(tmp_path):
    calls=[]
    runner, h, _ = build(tmp_path, handler=lambda i: calls.append(i))
    counter={'n':0}
    def scope(**kw):
        counter['n']+=1
        return counter['n'] == 1
    runner.gate.authorizer.scope_check = scope
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(AgentDenied):
            runner.execute(intent=intent(),vault_addr='x',role_id='r',
                           secret_id_supplier=lambda:'fresh-1')
    assert calls == []


def test_audit_failure_before_tool_blocks_execution(tmp_path):
    calls=[]
    class BrokenAudit:
        def append(self, **kw):
            raise OSError('disk full')
    runner,h,_=build(tmp_path,handler=lambda i:calls.append(i),audit=BrokenAudit())
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(OSError):
            runner.execute(intent=intent(),vault_addr='x',role_id='r',
                           secret_id_supplier=lambda:'fresh-1')
    assert not calls


def test_session_cleanup_error_not_success(tmp_path):
    runner,h,_=build(tmp_path)
    h.revoke_ok=False
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(RuntimeError,match='revocation failed'):
            runner.execute(intent=intent(),vault_addr='x',role_id='r',
                           secret_id_supplier=lambda:'fresh-1')


def test_tool_error_audited(tmp_path):
    def fail(i):
        raise RuntimeError('sensor offline')
    runner,h,_=build(tmp_path,handler=fail)
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(RuntimeError,match='sensor offline'):
            runner.execute(intent=intent(),vault_addr='x',role_id='r',
                           secret_id_supplier=lambda:'fresh-1')
    with sqlite3.connect(tmp_path/'tool.sqlite3') as db:
        event_types=[r[0] for r in db.execute('SELECT event_type FROM protected_tool_events')]
    assert 'FAILED' in event_types


def test_invalid_handlers_rejected(tmp_path):
    with pytest.raises(ValueError):
        ProtectedReadOnlyRunner(audit=None,decision_audit=None,delegation_check=lambda **k:True,
            scope_check=lambda **k:True,handlers={'enter_protected': lambda i:None})


def test_missing_supplier_denied(tmp_path):
    runner,h,_ = build(tmp_path)
    with pytest.raises(ToolDenied):
        runner.execute(intent=intent(),vault_addr='x',role_id='r',secret_id_supplier=None)


def test_denial_record_written(tmp_path):
    runner,h,_=build(tmp_path)
    with pytest.raises(ToolDenied):
        runner.execute(intent=intent(action='return_normal'),vault_addr='x',role_id='r',
                       secret_id_supplier=lambda:'fresh-1')
    with sqlite3.connect(tmp_path/'tool.sqlite3') as db:
        assert db.execute('SELECT event_type FROM protected_tool_events').fetchone()[0]=='DENIED'
