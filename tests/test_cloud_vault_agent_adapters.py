from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from applications.storeguard.cloud_dr.agent_execution_gate import AgentDenied, AgentIntent
from applications.storeguard.cloud_dr.vault_agent_adapters import (
    ExistingRegistryAdapter, ScopedReadOnlyAuthorizer, SqliteDecisionAudit,
    VaultRunAuthorizer,
)

AGENT = 'storeguard-weather-response-agent'
ENTITY = '260976f6-efa7-1bfe-d002-d28e58640e71'


def intent(**changes):
    data = dict(agent_id=AGENT, incident_id='INC1', store_id='1800',
                action='assess_weather', delegation_id='DEL1')
    data.update(changes)
    return AgentIntent(**data)


@contextmanager
def session(*args, **kwargs):
    yield SimpleNamespace(entity_id=ENTITY, policies=('storeguard-investigator',),
                          token_ttl=30, login_request_id='vault-request-123')


def make(tmp_path, delegation=True, scope=True):
    return VaultRunAuthorizer(
        audit=SqliteDecisionAudit(tmp_path / 'audit.sqlite3'),
        delegation_check=lambda **kw: delegation,
        scope_check=lambda **kw: scope,
    )


def test_authorization_with_fresh_session(tmp_path):
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.managed_approle_session', session), \
         patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        run_id = make(tmp_path).authorize(intent=intent(), vault_addr='http://127.0.0.1:8200',
                                          role_id='role', secret_id='secret')
    assert run_id
    import sqlite3
    with sqlite3.connect(tmp_path / 'audit.sqlite3') as db:
        assert db.execute('select decision from gate_decisions').fetchone() == ('allow',)


@pytest.mark.parametrize('override', [
    {'action':'enter_protected'}, {'action':'unknown'},
    {'delegation_id':''}, {'store_id':''}, {'incident_id':''},
])
def test_invalid_intent_denied(tmp_path, override):
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.managed_approle_session', session), \
         patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(AgentDenied):
            make(tmp_path).authorize(intent=intent(**override),
                                     vault_addr='a',role_id='b',secret_id='c')


@pytest.mark.parametrize('delegation,scope', [(False,True), (True,False), (False,False)])
def test_scope_or_delegation_denied(tmp_path, delegation, scope):
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.managed_approle_session', session), \
         patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(AgentDenied):
            make(tmp_path, delegation, scope).authorize(intent=intent(),
                           vault_addr='a', role_id='b', secret_id='c')


def test_registry_unknown_denied():
    assert not ExistingRegistryAdapter().is_active('unknown-agent')


def test_untrusted_missing_validators_denied():
    with pytest.raises(TypeError):
        ScopedReadOnlyAuthorizer(delegation_check=None,scope_check=lambda **k: True)


def test_no_login_request_id_denied(tmp_path):
    @contextmanager
    def missing(*a, **k):
        yield SimpleNamespace(entity_id=ENTITY, token_ttl=30, login_request_id=None)
    with patch('applications.storeguard.cloud_dr.vault_agent_adapters.managed_approle_session', missing), \
         patch('applications.storeguard.cloud_dr.vault_agent_adapters.verify_agent_identity'):
        with pytest.raises(AgentDenied):
            make(tmp_path).authorize(intent=intent(),vault_addr='a',role_id='b',secret_id='c')


def test_audit_is_append_only(tmp_path):
    audit = SqliteDecisionAudit(tmp_path / 'audit.sqlite3')
    rec={'run_id':'run1','decision':'deny'}
    audit.append(rec)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        audit.append(rec)
