"""Offline tests for fleet provisioning and signed HTTP exercise."""
import os
from pathlib import Path

import pytest

from scripts.enroll_store_fleet import enroll_fleet
from scripts.smoke_signed_fleet import run_smoke
from applications.storeguard.cloud_dr.store_identity import StoreIdentityRegistry


def test_enroll_four_independent_keys(tmp_path):
    ids = enroll_fleet(tmp_path / 'fleet', count=4)
    assert ids == ['1800', '1801', '1802', '1803']
    assert len({(tmp_path / 'fleet' / f'store-{i}.ed25519').read_bytes() for i in ids}) == 4


def test_private_file_modes(tmp_path):
    ids = enroll_fleet(tmp_path / 'fleet', count=2)
    assert os.stat(tmp_path / 'fleet').st_mode & 0o077 == 0
    for i in ids:
        assert os.stat(tmp_path / 'fleet' / f'store-{i}.ed25519').st_mode & 0o077 == 0


def test_refuses_overwrite(tmp_path):
    enroll_fleet(tmp_path / 'fleet', count=2)
    with pytest.raises(FileExistsError):
        enroll_fleet(tmp_path / 'fleet', count=2)


def test_offline_end_to_end_four_stores(tmp_path):
    ids = enroll_fleet(tmp_path / 'fleet', count=4)
    result = run_smoke(tmp_path / 'fleet', ids)
    assert result == {'stores': 4, 'commits': 4, 'replays_rejected': 4, 'idempotent_retries': 4}


def test_unknown_store_cannot_enroll_implicitly(tmp_path):
    ids = enroll_fleet(tmp_path / 'fleet', count=1)
    registry = StoreIdentityRegistry(tmp_path / 'fleet' / 'trusted_stores.sqlite3')
    row = registry.db.execute('SELECT count(*) FROM store_public_keys').fetchone()
    assert row[0] == 1
    registry.close()


def test_default_fleet_contains_40(tmp_path):
    ids = enroll_fleet(tmp_path / 'fleet')
    assert len(ids) == 40 and ids[0] == '1800' and ids[-1] == '1839'
