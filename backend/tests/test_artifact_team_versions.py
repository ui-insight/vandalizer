"""Team sharing grants one selected revision, including every read surface."""
import pytest

from app.services import artifacts, project_service
from app.services.access_control import TeamAccessContext
from tests.test_artifacts import db as db, route_env as route_env, make
from tests.test_chat_routes import _auth
from tests.test_project_resources import BrowseCollection


def versions(db):
    one = make(db, html='<p>Broken old version</p>')
    two = artifacts.revise(db, one, 'Reviewed dashboard', '<p>Reviewed content</p>', one['latest_revision'])
    two = artifacts.publish(db, two, two['latest_revision'])
    three = artifacts.revise(db, two, 'Confidential draft title', '<p>Unpublished secret</p>', two['latest_revision'])
    return three, [revision['uuid'] for revision in three['revisions']]


@pytest.mark.asyncio
async def test_team_can_only_read_the_selected_version_even_by_direct_url(client, db, route_env):
    doc, (old, shared, draft) = versions(db)
    cookies, headers = _auth()
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    response = await client.put(f'/api/pages/{doc["uuid"]}/team',
        json={'team_id': 'team-a'}, cookies=cookies, headers=headers)
    assert response.status_code == 200
    assert artifacts.get(db, doc['uuid'])['team_revision'] == shared
    owner = (await client.get(f'/api/pages/{doc["uuid"]}')).json()
    assert len(owner['revisions']) == 3 and owner['can_manage']

    route_env.user.user_id = 'QA1'
    member = (await client.get(f'/api/pages/{doc["uuid"]}')).json()
    assert member['latest_revision'] == member['team_revision'] == shared
    assert member['title'] == 'Reviewed dashboard'
    assert [r['version'] for r in member['revisions']] == [2]
    assert not member['can_manage'] and 'public_token' not in member
    assert member['source'] == {'kind': 'chat'}
    assert old not in str(member) and draft not in str(member)
    for revision in (old, draft):
        for suffix in ('content', 'content?download=true', 'source'):
            assert (await client.get(f'/api/pages/{doc["uuid"]}/revisions/{revision}/{suffix}')).status_code == 404
    for suffix in ('content', 'content?download=true'):
        response = await client.get(f'/api/pages/{doc["uuid"]}/revisions/{shared}/{suffix}')
        assert response.status_code == 200 and 'Reviewed content' in response.text
    assert (await client.get(f'/api/pages/{doc["uuid"]}/revisions/{shared}/source')).status_code == 404
    assert (await client.put(f'/api/pages/{doc["uuid"]}/team', json={'team_id': 'team-a', 'revision': draft}, cookies=cookies, headers=headers)).status_code == 404
    assert await project_service.authorize_resource('artifact', doc['uuid'], route_env.user) == 'Reviewed dashboard'


@pytest.mark.asyncio
async def test_owner_can_change_the_shared_version_without_sharing_history(client, db, route_env):
    doc, (old, shared, draft) = versions(db)
    cookies, headers = _auth()
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    for selected in (shared, draft):
        response = await client.put(f'/api/pages/{doc["uuid"]}/team', json={'team_id': 'team-a', 'revision': selected}, cookies=cookies, headers=headers)
        assert response.status_code == 200
        route_env.user.user_id = 'QA1'
        info = (await client.get(f'/api/pages/{doc["uuid"]}')).json()
        assert [r['uuid'] for r in info['revisions']] == [selected]
        if selected == draft:
            assert info['published_revision'] is None
        route_env.user.user_id = 'testuser'
    bad = await client.put(f'/api/pages/{doc["uuid"]}/team', json={'team_id': 'team-a', 'revision': 'missing'}, cookies=cookies, headers=headers)
    assert bad.status_code == 404
    assert artifacts.get(db, doc['uuid'])['team_revision'] == draft
    assert (await client.put(f'/api/pages/{doc["uuid"]}/team', json={'team_id': None}, cookies=cookies, headers=headers)).status_code == 200
    assert artifacts.get(db, doc['uuid'])['team_revision'] is None
    route_env.user.user_id = 'QA1'
    assert (await client.get(f'/api/pages/{doc["uuid"]}')).status_code == 404


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('published', [False, True])
def test_new_drafts_and_publication_changes_do_not_move_team_access(db, legacy, published):
    doc = make(db)
    if published:
        doc = artifacts.publish(db, doc, doc['latest_revision'])
    shared = doc['latest_revision']
    if legacy:
        db.html_artifacts.update_one({'uuid': doc['uuid']}, {'$set': {'team_id': 'team-a'}})
        doc = artifacts.get(db, doc['uuid'])
    else:
        doc = artifacts.share_team(db, doc, 'team-a')
    changed = artifacts.revise(db, doc, 'Private new title', '<p>Draft</p>', shared)
    assert changed['team_revision'] == shared
    changed = artifacts.publish(db, changed, changed['latest_revision'])
    assert changed['team_revision'] == shared
    artifacts.unpublish(db, changed)
    assert artifacts.metadata(artifacts.get(db, doc['uuid']))['latest_revision'] == shared


@pytest.mark.parametrize('action', ['publish', 'unpublish'])
def test_publication_changes_on_a_legacy_share_do_not_change_team_access(db, action):
    doc, (_, shared, draft) = versions(db)
    db.html_artifacts.update_one({'uuid': doc['uuid']}, {'$set': {'team_id': 'team-a'}})
    shared_doc = artifacts.get(db, doc['uuid'])
    if action == 'publish':
        artifacts.publish(db, shared_doc, draft)
    else:
        artifacts.unpublish(db, shared_doc)
    assert artifacts.metadata(artifacts.get(db, doc['uuid']))['latest_revision'] == shared


@pytest.mark.asyncio
async def test_browse_search_downloads_and_project_titles_do_not_disclose_drafts(client, db, route_env):
    db.html_artifacts = BrowseCollection()
    doc, (_, shared, draft) = versions(db)
    artifacts.share_team(db, doc, 'team-a', shared)
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    route_env.user.user_id = 'QA1'
    for url in ('/api/pages', '/api/pages/browse'):
        response = await client.get(url)
        assert response.status_code == 200
        assert draft not in response.text and 'Confidential' not in response.text and 'secret' not in response.text
        items = response.json() if url == '/api/pages' else response.json()['items']
        assert items[0]['latest_revision'] == shared and len(items[0]['revisions']) == 1
    hidden = (await client.get('/api/pages/browse?search=Confidential')).json()
    assert hidden['total'] == 0 and hidden['items'] == []
    visible = (await client.get('/api/pages/browse?search=Reviewed')).json()
    assert visible['total'] == 1 and visible['items'][0]['title'] == 'Reviewed dashboard'
    route_env.user.user_id = 'testuser'
    assert (await client.get('/api/pages/browse?search=Confidential')).json()['total'] == 1
    route_env.user.user_id = 'QA1'
    route_env.access.return_value = TeamAccessContext()
    assert (await client.get('/api/pages/browse')).json()['total'] == 0


@pytest.mark.asyncio
async def test_draft_edits_do_not_change_team_library_sort_order_or_dates(client, db, route_env):
    db.html_artifacts = BrowseCollection()
    first = artifacts.share_team(db, make(db, key='first'), 'team-a')
    second = artifacts.share_team(db, make(db, key='second'), 'team-a')
    artifacts.revise(db, first, 'Private update', '<p>Draft</p>', first['latest_revision'])
    route_env.user.user_id = 'QA1'
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    items = (await client.get('/api/pages/browse?sort=updated')).json()['items']
    assert [item['uuid'] for item in items] == [second['uuid'], first['uuid']]
    assert items[1]['updated_at'] == items[1]['revisions'][0]['created_at']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['chat', 'workflow', 'editor'])
@pytest.mark.parametrize('legacy', [False, True])
async def test_source_type_matches_for_owner_and_team_without_private_provenance(client, db, route_env, kind, legacy):
    db.html_artifacts = BrowseCollection()
    source = {'kind': kind, 'conversation_uuid': 'private-chat', 'workflow_id': 'private-workflow',
              'session_id': 'private-session', 'project_uuid': 'private-project',
              'skill': {'uuid': 'private-skill', 'version': 'v1'}}
    first = artifacts.create(db, 'testuser', 'Original', '<p>Original</p>', 'origin', source)
    second = artifacts.revise(db, first, 'Shared edit', '<p>Shared edit</p>', first['latest_revision'])
    artifacts.share_team(db, second, 'team-a')
    if legacy:
        db.html_artifacts.update_one({'uuid': first['uuid']}, {'$set': {'source': None}})
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    for viewer in ('testuser', 'QA1'):
        route_env.user.user_id = viewer
        for url in (f'/api/pages/{first["uuid"]}', '/api/pages', '/api/pages/browse'):
            response = await client.get(url)
            assert response.status_code == 200
            payload = response.json()
            item = payload['items'][0] if url.endswith('/browse') else payload[0] if url == '/api/pages' else payload
            assert item['source']['kind'] == kind
            if viewer == 'testuser':
                assert item['source'] == source
            else:
                assert item['source'] == {'kind': kind}
                assert 'private-' not in response.text
