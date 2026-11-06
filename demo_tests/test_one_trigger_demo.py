import pytest
from applications.storeguard.cloud_dr.one_trigger_demo import execute_demo

class Runner:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def execute(self,*,intent,evidence):
        self.calls.append((intent.action,evidence))
        if self.fail:raise PermissionError('revoked')
        result={'store_id':intent.store_id,'requires_human_review':True}
        if intent.action=='assess_weather':
            result={'store_id':intent.store_id,'weather_source':'fictional_deterministic_simulation',
                    'report':{'requires_human_review':True,'store_assessments':[{'store_id':intent.store_id}]}}
        return {'result':result,'action_run_id':intent.action+'-run',
                'authorization_run_id':'auth-'+intent.action,
                'action_gate_run_id':'gate-'+intent.action}

def test_one_trigger_completes_with_real_dependency_contract():
    events=[]; calls=[];runner=Runner()
    def submit(demo_run_id):
        calls.append(demo_run_id)
        return {'outcome':'acknowledged','region':'recovery','store_id':'1802','receipt_id':'receipt-123'}
    result=execute_demo(governed_runner=runner,evidence_factory=lambda x:x.agent_id,
        submit_order=submit,persist_event=lambda *args:events.append(args))
    assert result['transaction_store_id']=='1802'
    assert len(result['exposed_store_ids'])==6
    assert len(runner.calls)==2 and len(calls)==1
    assert [e[1] for e in events]==['THREAT_ASSESSED','AGENT_COMPLETED','AGENT_COMPLETED','DR_RECEIPT_VERIFIED']
    assert result['remaining_store_ids']==['SG-003','SG-004','SG-007','SG-008','SG-009']

def test_fail_closed_no_order_after_agent_denial():
    calls=[]
    with pytest.raises(PermissionError):
        execute_demo(governed_runner=Runner(fail=True),evidence_factory=lambda x:x.agent_id,
            submit_order=lambda x:calls.append(x),persist_event=lambda *args:None)
    assert calls==[]

def test_non_recovery_receipt_not_claimed_as_dr():
    events=[]
    with pytest.raises(RuntimeError,match='Recovery region'):
        execute_demo(governed_runner=Runner(),evidence_factory=lambda x:x.agent_id,
            submit_order=lambda x:{'outcome':'acknowledged','region':'primary','store_id':'SG-002','receipt_id':'x'},
            persist_event=lambda *args:events.append(args))
    assert events[-1][1]=='DR_NOT_VERIFIED'


def test_wrong_transaction_identity_fails_closed():
    calls=[]
    with pytest.raises(ValueError, match='1802'):
        execute_demo(governed_runner=Runner(), evidence_factory=lambda x:x.agent_id,
            submit_order=lambda x:calls.append(x), persist_event=lambda *args:None,
            transaction_store_id='SG-002')
    assert calls==[]
