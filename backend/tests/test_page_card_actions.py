"""Library management never rewrites saved versions or widens shared access."""
from copy import deepcopy

import pytest

from app.services import artifacts
from app.services.access_control import TeamAccessContext
from tests.test_artifacts import db as db, route_env as route_env, make
from tests.test_chat_routes import _auth
from tests.test_project_resources import BrowseCollection


async def test_rename_updates_owner_name_search_and_sort_without_a_revision(client, db, route_env):
    db.html_artifacts = BrowseCollection()
    doc = make(db)
    doc = artifacts.publish(db, doc, doc['latest_revision'])
    artifacts.share_team(db, doc, 'team-a', doc['latest_revision'])
    before = deepcopy(artifacts.get(db, doc['uuid']))
    cookies, headers = _auth()
    renamed = await client.patch(f'/api/pages/{doc["uuid"]}', json={'title': '  Renamed dashboard  '}, cookies=cookies, headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()['title'] == 'Renamed dashboard'
    saved = artifacts.get(db, doc['uuid'])
    assert saved['revisions'] == before['revisions']
    assert saved['latest_revision'] == before['latest_revision']
    assert saved['published_revision'] == before['published_revision']
    assert saved['public_token'] == before['public_token']
    assert saved['team_revision'] == before['team_revision']
    assert saved['updated_at'] >= before['updated_at']
    assert (await client.get('/api/pages/browse?search=Renamed&sort=title')).json()['items'][0]['title'] == 'Renamed dashboard'
    assert (await client.get('/api/pages/browse?search=Review')).json()['total'] == 0
    assert (await client.get(f'/api/pages/{doc["uuid"]}/revisions/{doc["latest_revision"]}/source')).json()['title'] == 'Renamed dashboard'
    public = (await client.get(f'/api/pages/public/{doc["public_token"]}')).json()
    assert public['title'] == 'Review'
    route_env.user.user_id = 'team-reader'
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    assert (await client.get('/api/pages/browse?search=Renamed')).json()['total'] == 0
    assert (await client.get(f'/api/pages/{doc["uuid"]}')).json()['title'] == 'Review'
    assert (await client.patch(f'/api/pages/{doc["uuid"]}', json={'title': 'Forbidden'}, cookies=cookies, headers=headers)).status_code == 404


@pytest.mark.parametrize('title', ['', '   ', 'x' * 201])
async def test_rename_rejects_empty_or_long_names(client, db, route_env, title):
    doc = make(db)
    cookies, headers = _auth()
    assert (await client.patch(f'/api/pages/{doc["uuid"]}', json={'title': title}, cookies=cookies, headers=headers)).status_code == 422
    assert artifacts.get(db, doc['uuid']) == doc


async def test_duplicate_copies_latest_once_as_private_without_source_associations(client, db, route_env):
    doc = make(db)
    doc = artifacts.revise(db, doc, 'Updated dashboard', '<h1>Latest data</h1><p>$121,600</p>', doc['latest_revision'])
    doc = artifacts.publish(db, doc, doc['latest_revision'])
    artifacts.share_team(db, doc, 'team-a')
    doc = artifacts.rename(db, doc, 'Award dashboard')
    before = deepcopy(artifacts.get(db, doc['uuid']))
    cookies, headers = _auth()
    async def copy(key):
        return await client.post(f'/api/pages/{doc["uuid"]}/duplicate', json={'request_id': key}, cookies=cookies, headers=headers)
    response = await copy('copy-1')
    assert response.status_code == 200
    saved = artifacts.get(db, response.json()['uuid'])
    assert saved['uuid'] != doc['uuid'] and saved['title'] == 'Copy of Award dashboard'
    assert len(saved['revisions']) == 1 and '$121,600' in artifacts.revision(saved)['html']
    assert saved['team_id'] is None and saved['team_revision'] is None and saved['project_uuid'] is None
    assert saved['public_token'] is None and saved['published_revision'] is None and saved['publications'] == []
    assert 'conversation_uuid' not in saved['source'] and saved['source']['kind'] == 'editor'
    assert artifacts.get(db, doc['uuid']) == before
    # A retry after a source edit still returns the same copy.
    artifacts.revise(db, before, 'New source', '<h1>Later data</h1>', before['latest_revision'])
    assert (await copy('copy-1')).json()['uuid'] == saved['uuid']
    assert (await copy('copy-2')).json()['uuid'] != saved['uuid']
    assert len(db.html_artifacts.docs) == 3


async def test_team_duplicate_only_copies_the_shared_version_and_revocation_is_enforced(client, db, route_env):
    doc = make(db, html='<h1>Shared report</h1>')
    shared = doc['latest_revision']
    artifacts.share_team(db, doc, 'team-a', shared)
    doc = artifacts.revise(db, artifacts.get(db, doc['uuid']), 'Secret draft', '<h1>Secret content</h1>', shared)
    route_env.user.user_id = 'team-reader'
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    cookies, headers = _auth()
    url = f'/api/pages/{doc["uuid"]}/duplicate'
    copied = await client.post(url, json={'request_id': 'copy-1'}, cookies=cookies, headers=headers)
    assert copied.status_code == 200 and copied.json()['title'] == 'Copy of Review'
    new = artifacts.get(db, copied.json()['uuid'])
    assert new['user_id'] == 'team-reader' and new['source']['copied_revision'] == shared
    assert 'Secret' not in str(new) and 'Shared report' in artifacts.revision(new)['html']
    route_env.access.return_value = TeamAccessContext()
    assert (await client.post(url, json={'request_id': 'copy-2'}, cookies=cookies, headers=headers)).status_code == 404


async def test_deleted_pages_cannot_be_renamed_or_duplicated(client, db, route_env):
    doc = make(db)
    cookies, headers = _auth()
    assert (await client.delete(f'/api/pages/{doc["uuid"]}', cookies=cookies, headers=headers)).status_code == 200
    assert (await client.patch(f'/api/pages/{doc["uuid"]}', json={'title': 'Rename'}, cookies=cookies, headers=headers)).status_code == 404
    assert (await client.post(f'/api/pages/{doc["uuid"]}/duplicate', json={'request_id': 'copy'}, cookies=cookies, headers=headers)).status_code == 404
