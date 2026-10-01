"""Exercise real local APIs and Mongo persistence using disposable QA accounts.

Requires isolated-backend.py. Mutates only that process's synthetic data.
Tokens/passwords stay in private temporary files, never the evidence report.
"""
import datetime as dt
import json
from pathlib import Path
import uuid

import httpx
from pymongo import MongoClient

run = Path('/private/tmp/vandalizer-ra8-backend')
runtime = json.loads((run / 'runtime.json').read_text())
db_client = MongoClient('mongodb://127.0.0.1:27028/')
db = db_client['vandalizer_ra8_20261001']
checks = []
clients = {}
state = {}
completed = False

def call(client, method, path, body=None, codes=(200,), label=None):
    csrf = client.cookies.get('csrf_token')
    response = client.request(method, '/api' + path, json=body, headers={'X-CSRF-Token': csrf} if csrf else {})
    assert response.status_code in codes, f'{label or path}: HTTP {response.status_code}: {response.text[:250]}'
    if label:
        checks.append(label)
        print('Passed:', label, flush=True)
    return response.json()

try:
    # Each identity has a real password login and independently issued cookies.
    for role in ['owner', 'member', 'viewer', 'outsider']:
        client = httpx.Client(base_url='http://127.0.0.1:8001', follow_redirects=True, timeout=20)
        clients[role] = client
        call(client, 'POST', '/auth/login', {'user_id': f'ra8-{role}@example.test', 'password': runtime['password']}, label=f'{role} signs in with an independent session')
    owner, member, viewer, outsider = [clients[key] for key in ['owner', 'member', 'viewer', 'outsider']]
    suffix = uuid.uuid4().hex[:6]
    team = call(owner, 'POST', '/teams/create', {'name': f'QA Research office {suffix}'}, label='owner creates a team')
    second = call(owner, 'POST', '/teams/create', {'name': f'QA Second team {suffix}'})
    state.update(team=team, second_team=second)
    tid, tuuid = team['id'], team['uuid']
    call(outsider, 'GET', f'/teams/{tuuid}/members', codes=(403,), label='nonmember cannot read team members')
    invite = call(owner, 'POST', '/teams/invite', {'team_id': tuuid, 'email': 'ra8-member@example.test', 'role': 'member'}, label='email invitation is issued to the local mail sink')
    call(viewer, 'POST', f'/teams/invite/accept/{invite["token"]}', codes=(400,), label='a different email cannot accept the invitation')
    call(member, 'POST', f'/teams/invite/accept/{invite["token"]}', label='intended member accepts invitation')
    assert call(member, 'GET', f'/teams/{tuuid}/members')
    call(member, 'POST', '/teams/member/role', {'team_id': tuuid, 'user_id': 'ra8-owner@example.test', 'role': 'member'}, codes=(400,), label='ordinary member cannot change roles')
    call(owner, 'POST', '/teams/member/role', {'team_id': tuuid, 'user_id': 'ra8-member@example.test', 'role': 'admin'}, label='owner changes member role')
    members = call(owner, 'GET', f'/teams/{tuuid}/members')
    assert next(row for row in members if row['user_id'] == 'ra8-member@example.test')['role'] == 'admin'
    link = call(owner, 'POST', f'/teams/{tuuid}/join-link', {'role': 'member', 'max_uses': 1})
    call(viewer, 'POST', f'/teams/join-link/accept/{link["token"]}', label='controlled viewer accepts team join link')
    call(outsider, 'POST', f'/teams/join-link/accept/{link["token"]}', codes=(400,), label='exhausted link cannot add another account')
    expired = call(owner, 'POST', f'/teams/{tuuid}/join-link', {'role': 'member'})
    assert db.team_join_link.update_one({'token': expired['token']}, {'$set': {'expires_at': dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)}}).modified_count == 1
    call(outsider, 'POST', f'/teams/join-link/accept/{expired["token"]}', codes=(400,), label='expired team link is refused by the backend')
    revoked = call(owner, 'POST', f'/teams/{tuuid}/join-link', {'role': 'member'})
    call(owner, 'DELETE', f'/teams/join-link/{revoked["token"]}')
    call(outsider, 'POST', f'/teams/join-link/accept/{revoked["token"]}', codes=(400,), label='revoked team link is refused by the backend')
    for target in [second, team]:
        call(owner, 'POST', f'/teams/switch/{target["uuid"]}')
        me = call(owner, 'GET', '/auth/me')
        assert me.get('current_team') in (target['id'], target['uuid']) or me.get('current_team_uuid') == target['uuid']
    checks.append('team switching persists the intended current team')
    call(owner, 'POST', '/teams/transfer-ownership', {'team_uuid': tuuid, 'new_owner_user_id': 'ra8-member@example.test'}, label='ownership transfers to the intended controlled account')
    members = call(member, 'GET', f'/teams/{tuuid}/members')
    assert next(row for row in members if row['user_id'] == 'ra8-member@example.test')['role'] == 'owner'
    assert next(row for row in members if row['user_id'] == 'ra8-owner@example.test')['role'] != 'owner'
    call(member, 'POST', '/teams/member/remove', {'team_id': tuuid, 'user_id': 'ra8-viewer@example.test'})
    call(viewer, 'GET', f'/teams/{tuuid}/members', codes=(403,), label='removed team member loses access')

    viewer_invite = call(member, 'POST', '/teams/invite', {'team_id': tuuid, 'email': 'ra8-viewer@example.test', 'role': 'admin'})
    call(viewer, 'POST', f'/teams/invite/accept/{viewer_invite["token"]}')
    call(member, 'POST', '/teams/member/role', {'team_id': tuuid, 'user_id': 'ra8-viewer@example.test', 'role': 'member'})
    call(viewer, 'POST', f'/teams/invite/accept/{viewer_invite["token"]}')
    assert next(row for row in call(member, 'GET', f'/teams/{tuuid}/members') if row['user_id'] == 'ra8-viewer@example.test')['role'] == 'member'
    checks.append('reused invitation does not restore an old elevated role')
    call(member, 'POST', '/teams/member/remove', {'team_id': tuuid, 'user_id': 'ra8-viewer@example.test'})
    call(viewer, 'POST', f'/teams/invite/accept/{viewer_invite["token"]}', codes=(400,), label='removed member cannot regain access with a consumed email invitation')

    project = call(owner, 'POST', '/projects', {'title': f'QA Sponsor review {suffix}', 'description': 'Controlled collaboration QA; no real proposal data.'})
    pid = project['uuid']
    state['project'] = project
    call(outsider, 'GET', f'/projects/{pid}', codes=(404,), label='private project is unavailable to a nonmember')
    for client, role in [(member, 'editor'), (viewer, 'viewer')]:
        link = call(owner, 'POST', f'/projects/{pid}/invite-link', {'role': role, 'max_uses': 1})
        call(client, 'POST', f'/projects/join/accept/{link["token"]}', label=f'{role} accepts project invitation')
        assert call(client, 'GET', f'/projects/{pid}')['role'] == role
    call(viewer, 'PATCH', f'/projects/{pid}', {'description': 'Unauthorized change'}, codes=(403,), label='viewer cannot edit the project')
    call(member, 'PATCH', f'/projects/{pid}', {'description': 'Editor reviewed the required sponsor evidence.'}, label='editor change persists')
    assert call(owner, 'GET', f'/projects/{pid}')['description'] == 'Editor reviewed the required sponsor evidence.'
    call(member, 'DELETE', f'/projects/{pid}', codes=(403,), label='editor cannot delete the owner’s project')
    link = call(owner, 'POST', f'/projects/{pid}/invite-link', {'role': 'viewer'})
    assert db.project_join_link.update_one({'token': link['token']}, {'$set': {'expires_at': dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)}}).modified_count == 1
    call(outsider, 'POST', f'/projects/join/accept/{link["token"]}', codes=(400,), label='expired project invite is refused')
    call(owner, 'DELETE', f'/projects/{pid}/members/ra8-viewer@example.test')
    call(viewer, 'GET', f'/projects/{pid}', codes=(404,), label='removed project viewer loses access')
    call(owner, 'GET', '/projects/unavailable-project', codes=(404,), label='unavailable project is explicitly absent')

    call(outsider, 'POST', '/certification/modules/ai_literacy/assessment', {'answers': {}})
    call(outsider, 'POST', '/certification/modules/ai_literacy/complete', codes=(400,), label='incomplete assessment cannot complete the module')
    answers = {'experience': 'Occasional use', 'comfort': 'Check every source', 'concern': 'Unsupported deadlines'}
    call(outsider, 'POST', '/certification/modules/ai_literacy/assessment', {'answers': answers})
    assessment = call(outsider, 'GET', '/certification/progress')['modules']['ai_literacy']['self_assessment']
    assert all(assessment[key] == value for key, value in answers.items())
    assert assessment['completed_at']
    call(outsider, 'POST', '/certification/modules/ai_literacy/complete', label='representative learning assessment completes and persists')
    saved = call(outsider, 'GET', '/certification/progress')
    assert saved['modules']['ai_literacy']['completed'] and saved['total_xp'] > 0
    call(outsider, 'POST', '/certification/modules/ai_literacy/complete')
    assert call(outsider, 'GET', '/certification/progress')['total_xp'] == saved['total_xp']
    checks.append('repeated completion does not award duplicate XP')
    assert list((run / 'mail').glob('*.eml')), 'Invitation was not delivered to the local mail sink'
    (run / 'collaboration-state.json').write_text(json.dumps(state))
    completed = True
finally:
    for client in clients.values():
        client.close()
    db_client.close()
    report = {'completed': completed, 'mode': 'Real local FastAPI, MongoDB and Redis; five synthetic accounts; SMTP captured locally; outbound connections restricted. No model or production execution.', 'passed_checks': checks, 'count': len(checks), 'timestamp': dt.datetime.now(dt.timezone.utc).isoformat()}
    out = Path('artifacts/visual-review/2026-10-01-ra8-isolated-collaboration')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'api-evidence.json').write_text(json.dumps(report, indent=2))
