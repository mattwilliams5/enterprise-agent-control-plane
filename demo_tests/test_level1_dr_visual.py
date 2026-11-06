"""Level 1 regional DR evidence regression tests."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

path = (
    Path(__file__).resolve().parents[1]
    / "deployments/storeguard/hosted-executive/ui/storeguard/cloud_dr_visual.py"
)
spec = spec_from_file_location("storeguard_dr_visual_test", path)
module = module_from_spec(spec)
spec.loader.exec_module(module)
regional_evidence = module.regional_evidence


@pytest.fixture
def summary():
    return {
        "verified": True,
        "exposed": ["SG-002", "SG-003", "SG-004"],
        "agents": [{
            "agent_id": "storeguard-weather-response-agent",
            "action": "assess_weather",
            "action_run_id": "action-1",
            "authorization_run_id": "auth-1",
            "action_gate_run_id": "gate-1",
        }],
        "receipt": {
            "status": "recovery_transaction_verified",
            "transaction_store_id": "1802",
            "order": {
                "outcome": "acknowledged",
                "region": "recovery",
                "receipt_id": "receipt-1",
                "attempts": [
                    {
                        "region": "primary",
                        "error": "SIMULATED_CLIENT_SIDE_OUTAGE",
                    },
                    {"region": "recovery", "status_code": 200},
                ],
            },
        },
    }


def test_verified_recovery_path(summary):
    result = regional_evidence(summary)
    assert result["primary_simulated"]
    assert result["recovery_200"]
    assert result["verified"]
    assert result["receipt_id"] == "receipt-1"
    assert result["store_client"] == "1802"
    assert len(result["governed_agents"]) == 1


def test_missing_receipt_fails_closed(summary):
    summary["receipt"]["order"]["receipt_id"] = None
    assert not regional_evidence(summary)["verified"]


def test_recovery_http_failure_fails_closed(summary):
    summary["receipt"]["order"]["attempts"][1]["status_code"] = 503
    assert not regional_evidence(summary)["verified"]


def test_missing_authorization_not_counted(summary):
    del summary["agents"][0]["authorization_run_id"]
    assert not regional_evidence(summary)["governed_agents"]


def test_primary_outage_not_invented(summary):
    summary["receipt"]["order"]["attempts"].pop(0)
    assert not regional_evidence(summary)["primary_simulated"]
