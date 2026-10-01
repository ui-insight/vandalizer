"""Real password recovery with local SMTP; private tokens never enter evidence."""
import datetime as dt
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import re
import secrets
import httpx
import jwt
run = Path('/private/tmp/vandalizer-ra8-backend')
runtime = json.loads((run / 'runtime.json').read_text())
checks = []
completed = False
client = httpx.Client(base_url='http://127.0.0.1:8001/api', timeout=20)
public = httpx.Client(base_url='http://127.0.0.1:8001/api', timeout=20)
identity = 'ra8-outsider@example.test'

def call(c, method, path, data=None, code=200, label=None):
    csrf = c.cookies.get('csrf_token')
    r = c.request(method, path, json=data, headers={'X-CSRF-Token': csrf} if csrf else {})
    assert r.status_code == code, f'{label or path}: expected {code}, got {r.status_code}'
    if label:
        checks.append(label)
        print('Passed:', label, flush=True)
    return r.json()

def reset_token():
    before = set((run / 'mail').glob('*.eml'))
    call(public, 'POST', '/auth/forgot-password', {'email': identity})
    for file in set((run / 'mail').glob('*.eml')) - before:
        mail = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
        for part in mail.walk():
            if part.get_content_type() in ('text/plain', 'text/html'):
                match = re.search(r'reset-password\?token=([A-Za-z0-9_-]+)', part.get_content())
                if match:
                    return match.group(1)
    raise AssertionError('No reset link captured by local SMTP')

try:
    call(public, 'GET', '/auth/config')
    call(client, 'POST', '/auth/login', {'user_id': identity, 'password': runtime['password']}, label='password sign-in issues a real session')
    call(client, 'GET', '/auth/me', label='signed-in account loads from persisted session')
    saved_cookies = dict(client.cookies)
    expired = jwt.encode({'sub': identity, 'exp': dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=1), 'type': 'access', 'ver': 0}, runtime['jwt_secret'], algorithm='HS256')
    client.cookies.clear()
    for key, value in saved_cookies.items():
        client.cookies.set(key, expired if key == 'access_token' else value, domain='127.0.0.1', path='/')
    call(client, 'GET', '/auth/me', code=401, label='expired access token is refused')
    call(client, 'POST', '/auth/refresh', label='valid refresh session restores access')
    token = reset_token()
    checks.append('reset email is delivered only to the local SMTP sink')
    call(public, 'POST', '/auth/reset-password', {'token': token, 'password': 'weak'}, code=422, label='weak password is rejected before consuming the link')
    new_password = 'Qa9!' + secrets.token_urlsafe(24)
    call(public, 'POST', '/auth/reset-password', {'token': token, 'password': new_password}, label='emailed reset token updates the password')
    call(public, 'POST', '/auth/reset-password', {'token': token, 'password': new_password}, code=400, label='used reset link cannot be replayed')
    call(client, 'GET', '/auth/me', code=401, label='password reset invalidates the old access session')
    call(client, 'POST', '/auth/refresh', code=401, label='password reset invalidates the old refresh session')
    call(public, 'POST', '/auth/login', {'user_id': identity, 'password': runtime['password']}, code=401, label='old password no longer signs in')
    call(public, 'POST', '/auth/login', {'user_id': identity, 'password': new_password}, label='new password signs in')
    # Return this disposable fixture to its stable password for later UI checks.
    token = reset_token()
    call(public, 'POST', '/auth/reset-password', {'token': token, 'password': runtime['password']})
    call(public, 'POST', '/auth/reset-password', {'token': 'expired-qa-token', 'password': runtime['password']}, code=400, label='invalid or expired reset link is refused')
    config = call(public, 'GET', '/auth/config')
    assert not any(p.get('configured') for p in config.get('oauth_providers', []))
    checks.append('local configuration exposes no configured SSO provider; provider handshake not tested')
    completed = True
finally:
    client.close(); public.close()
    out = Path('artifacts/visual-review/2026-10-01-ra8-isolated-auth')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'api-evidence.json').write_text(json.dumps({'completed': completed, 'mode': 'Real local auth, Mongo/Redis and captured SMTP; synthetic account; no external identity provider', 'passed_checks': checks, 'count': len(checks)}, indent=2))
