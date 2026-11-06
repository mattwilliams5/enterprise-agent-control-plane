"""Typed client. Only use from IAM-protected hosted executive service."""
import os
from urllib.parse import urlparse
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

def _base_url():
    url = os.environ.get('STOREGUARD_CONTROL_URL', '').rstrip('/')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.run.app') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise RuntimeError('Valid Cloud Run control URL required')
    return url

def call(method, path, payload=None):
    base = _base_url()
    if not path.startswith('/exercises'):
        raise ValueError('Unapproved command path')
    token = id_token.fetch_id_token(Request(), base)
    r = requests.request(method, base + path, headers={'Authorization': f'Bearer {token}'}, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()
