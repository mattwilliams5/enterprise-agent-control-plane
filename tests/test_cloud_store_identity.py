"""Offline Batch 5 tests; no GCP calls or changes to existing application routes."""
import concurrent.futures
import json
import sqlite3

import pytest

from applications.storeguard.cloud_dr.store_identity import (
    StoreAuthenticationError, StoreIdentityRegistry,
    generate_private_key, public_key_bytes, sign_order_request,
)

BODY = b'{"order_id":"ORDER-1","amount_cents":2599,"idempotency_key":"KEY-1"}'
NOW = 1800000000


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / 'identity.db'
    key = generate_private_key()
    registry = StoreIdentityRegistry(path)
    registry.enroll('1847', 'key-a', public_key_bytes(key))
    yield registry, key, path
    registry.close()


def headers(key, **kw):
    return sign_order_request(key, store_id=kw.get('store_id','1847'),
                              key_id=kw.get('key_id','key-a'),
                              body=kw.get('body',BODY),
                              timestamp=kw.get('timestamp',NOW),
                              nonce=kw.get('nonce','N' * 24))


def verify(registry, h, **kw):
    return registry.verify(headers=h, body=kw.get('body',BODY),
                           method=kw.get('method','POST'),
                           path=kw.get('path','/orders'), now=kw.get('now',NOW))


def test_valid_signature_binds_store(setup):
    registry, key, _ = setup
    assert verify(registry, headers(key)).store_id == '1847'


def test_raw_body_tamper_rejected(setup):
    registry, key, _ = setup
    with pytest.raises(StoreAuthenticationError):
        verify(registry, headers(key), body=BODY+b' ')


def test_store_header_tamper_rejected(setup):
    registry, key, _ = setup
    h = headers(key)
    h['X-Store-ID'] = '1848'
    with pytest.raises(StoreAuthenticationError):
        verify(registry, h)


def test_key_identity_cannot_impersonate_other_store(setup):
    registry, key, _ = setup
    with pytest.raises(StoreAuthenticationError):
        verify(registry, headers(key,store_id='1848'))


def test_replay_rejected(setup):
    registry, key, _ = setup
    h = headers(key)
    verify(registry,h)
    with pytest.raises(StoreAuthenticationError):
        verify(registry,h)


def test_replay_persists_after_restart(setup):
    registry, key, path = setup
    h = headers(key)
    verify(registry,h)
    second = StoreIdentityRegistry(path)
    try:
        with pytest.raises(StoreAuthenticationError):
            verify(second,h)
    finally:
        second.close()


def test_fresh_nonce_allows_same_order_body(setup):
    registry, key, _ = setup
    verify(registry,headers(key,nonce='A'*24))
    assert verify(registry,headers(key,nonce='B'*24)).store_id == '1847'


def test_expired_and_future_signatures_rejected(setup):
    registry, key, _ = setup
    for ts in (NOW-121,NOW+121):
        with pytest.raises(StoreAuthenticationError):
            verify(registry,headers(key,timestamp=ts))


def test_revocation_blocks_new_requests(setup):
    registry, key, _ = setup
    registry.revoke('1847','key-a')
    with pytest.raises(StoreAuthenticationError):
        verify(registry,headers(key))


def test_rotation_new_key_id_without_replacing_old(setup):
    registry, key, _ = setup
    other = generate_private_key()
    registry.enroll('1847','key-b',public_key_bytes(other))
    registry.revoke('1847','key-a')
    with pytest.raises(StoreAuthenticationError):
        verify(registry,headers(key))
    assert verify(registry,headers(other,key_id='key-b')).key_id == 'key-b'


def test_reenroll_fails_closed(setup):
    registry, key, _ = setup
    with pytest.raises(sqlite3.IntegrityError):
        registry.enroll('1847','key-a',public_key_bytes(generate_private_key()))


def test_unsigned_or_invalid_signature_fails(setup):
    registry, key, _ = setup
    with pytest.raises(StoreAuthenticationError):
        verify(registry,{})
    bad = headers(key)
    bad['X-Store-Signature']='invalid'
    with pytest.raises(StoreAuthenticationError):
        verify(registry,bad)


def test_method_and_path_bound(setup):
    registry, key, _ = setup
    for method, path in [('GET','/orders'),('POST','/admin')]:
        with pytest.raises(StoreAuthenticationError):
            verify(registry,headers(key),method=method,path=path)


def test_store_key_unique_across_stores(setup):
    registry, key, _ = setup
    other = generate_private_key()
    registry.enroll('1848','key-a',public_key_bytes(other))
    assert verify(registry,headers(other,store_id='1848')).store_id == '1848'


def test_simultaneous_same_nonce_one_winner(tmp_path):
    path=tmp_path/'concurrent.db'
    primary=StoreIdentityRegistry(path)
    key=generate_private_key()
    primary.enroll('1847','key-a',public_key_bytes(key))
    h=headers(key)
    primary.close()
    def attempt(_):
        r=StoreIdentityRegistry(path)
        try:
            verify(r,h)
            return 'accepted'
        except StoreAuthenticationError:
            return 'rejected'
        finally:
            r.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(attempt,range(8)))
    assert outcomes.count('accepted') == 1
    assert outcomes.count('rejected') == 7
