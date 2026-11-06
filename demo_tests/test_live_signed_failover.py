import json
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from applications.storeguard.cloud_dr.live_signed_failover import PrivateRegion, submit_signed_failover
from applications.storeguard.cloud_dr.store_identity import signature_message, _decode_b64url

P = PrivateRegion('primary', 'https://orders-primary.example.com')
R = PrivateRegion('recovery', 'https://orders-recovery.example.com')


def exercise(*, simulate=False, primary_status=503, recovery_status=200):
    key = Ed25519PrivateKey.generate()
    seen=[]
    tokens=[]
    def token(audience):
        tokens.append(audience)
        return 'test-token'
    def handler(request):
        data=json.loads(request.content)
        h=request.headers
        key.public_key().verify(_decode_b64url(h['x-store-signature']),signature_message(
            store_id=h['x-store-id'],key_id=h['x-store-key-id'],timestamp=int(h['x-store-timestamp']),
            nonce=h['x-store-nonce'],method='POST',path='/orders',body=request.content))
        assert h['authorization']=='Bearer test-token'
        seen.append((request.url.host,h['x-store-nonce'],data))
        status=primary_status if request.url.host.startswith('orders-primary') else recovery_status
        return httpx.Response(status, json={'status':'committed','order_id':data['order_id'],
            'store_id':h['x-store-id'],'receipt_id':'r123'})
    result=submit_signed_failover(primary=P,recovery=R,store_id='SG-002',key_id='demo-key',
        private_key=key,order_id='demo-order-1',amount_cents=42,idempotency_key='demo-idempotency-1',
        identity_token=token,transport=httpx.MockTransport(handler),simulate_primary_outage=simulate)
    return result,seen,tokens

def test_failover_503_resigns_same_order():
    result,seen,tokens=exercise()
    assert result['outcome']=='acknowledged' and result['region']=='recovery'
    assert len(seen)==2 and seen[0][1]!=seen[1][1]
    assert seen[0][2]==seen[1][2]
    assert tokens==[P.url,R.url]

def test_simulated_primary_outage_does_not_contact_primary():
    result,seen,tokens=exercise(simulate=True)
    assert result['outcome']=='acknowledged'
    assert len(seen)==1 and seen[0][0]=='orders-recovery.example.com'
    assert tokens==[R.url]
    assert result['attempts'][0]['error']=='SIMULATED_CLIENT_SIDE_OUTAGE'

def test_auth_failure_never_fails_over():
    result,seen,tokens=exercise(primary_status=403)
    assert result['outcome']=='rejected' and result['status_code']==403
    assert len(seen)==1 and tokens==[P.url]

def test_unverified_receipt_not_success():
    result,seen,tokens=exercise(recovery_status=200,primary_status=500)
    assert result['outcome']=='unknown' and len(seen)==1
