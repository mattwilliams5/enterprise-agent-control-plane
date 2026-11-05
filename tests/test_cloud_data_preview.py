from unittest.mock import patch
import pytest
from ui.storeguard.cloud_data import _cloud_run_url, latest_runs


def test_rejects_local_and_untrusted_urls():
    for value in ['http://127.0.0.1:8080', 'https://example.com', 'https://x.run.app/extra']:
        with patch.dict('os.environ', {'SG_TEST_URL': value}):
            with pytest.raises(ValueError): _cloud_run_url('SG_TEST_URL')


class Collection:
    def order_by(self, *args, **kwargs): return self
    def limit(self, n): return self
    def stream(self):
        return [type('Doc', (), {'to_dict':lambda self: {'source':'verified_local_sqlite_failover',
         'mode':'simulated_primary_route_failure','run_id':'abc123abc123',
         'primary_commits':20,'recovered_commits':20,'queued_during_outage':20,
         'cross_region_duplicates':40,'replays_rejected':40,'pending':0}})()]
class Client:
    def collection(self, name):
        assert name == 'storeguard_executive_demo_runs'
        return Collection()


def test_run_summary_only_approved_fields():
    results = latest_runs(client=Client())
    assert results[0]['run_id'] == 'abc123abc123'
    assert results[0]['recovered_commits'] == 20


def test_limit_validation():
    with pytest.raises(ValueError): latest_runs(client=Client(), limit=0)
