"""Project resource references preserve ACLs and defaults never rewrite a chat."""
import re
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services import artifacts, project_service
from app.services.access_control import TeamAccessContext
from tests import test_artifacts as artifact_tests
from tests.test_chat_routes import _auth
from tests.test_chat_skills import snapshot


Collection = artifact_tests.Collection
db = artifact_tests.db
route_env = artifact_tests.route_env


class BrowseCollection(Collection):
    def matches(self, doc, query):
        for key, value in query.items():
            if key == '$and':
                if not all(self.matches(doc, q) for q in value):
                    return False
            elif isinstance(value, dict) and '$regex' in value:
                if not re.search(value['$regex'], doc.get(key, ''), re.I):
                    return False
            elif not super().matches(doc, {key: value}):
                return False
        return True

    def aggregate(self, pipeline):
        assert pipeline[1] == {'$project': {'revisions.html': 0}}
        assert pipeline[2] == {'$addFields': {'title': {'$ifNull': ['$title', {'$arrayElemAt': ['$revisions.title', -1]}]}}}
        docs = [deepcopy(d) for d in self.docs if self.matches(d, pipeline[0]['$match'])]
        for doc in docs:
            for revision in doc['revisions']:
                revision.pop('html')
            doc.setdefault('title', doc['revisions'][-1]['title'])
        for step in pipeline[3:-1]:
            docs = [doc for doc in docs if self.matches(doc, step['$match'])]
        total = len(docs)
        operations = pipeline[-1]['$facet']['items']
        for key, direction in reversed(list(operations[0]['$sort'].items())):
            docs.sort(key=lambda d: d[key], reverse=direction < 0)
        offset, limit = operations[1]['$skip'], operations[2]['$limit']
        return iter([{'items': docs[offset:offset + limit], 'total': [{'value': total}]}])


@pytest.mark.asyncio
async def test_pages_pagination_search_and_team_revocation(client, db, route_env):
    db.html_artifacts = BrowseCollection()
    for i in range(121):
        artifacts.create(db, 'testuser', f'Page {i:03}', '<p>Private</p>', str(i))
    other = artifacts.create(db, 'other', 'Hidden', '<p>Hidden</p>', 'other', {'conversation_uuid': 'secret'})
    result = (await client.get('/api/pages/browse?page=6&sort=title')).json()
    assert result['total'] == 121 and len(result['items']) == 20
    assert result['items'][0]['title'] == 'Page 100'
    assert 'Private' not in str(result)
    literal = artifacts.create(db, 'testuser', 'Report (C++)', '<p>x</p>', 'literal')
    # An earlier saved page has no top-level title; search still finds it.
    next(d for d in db.html_artifacts.docs if d['uuid'] == literal['uuid']).pop('title')
    result = (await client.get('/api/pages/browse', params={'search': '(C++)'})).json()
    assert [d['uuid'] for d in result['items']] == [literal['uuid']]
    db.html_artifacts.update_one({'uuid': other['uuid']}, {'$set': {'team_id': 'team-a'}})
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    visible = (await client.get('/api/pages/browse?search=Hidden')).json()['items']
    assert len(visible) == 1 and 'source' not in visible[0]
    route_env.access.return_value = TeamAccessContext()
    assert (await client.get('/api/pages/browse?search=Hidden')).json()['items'] == []
    assert (await client.get('/api/pages/browse?page=0')).status_code == 422


@pytest.mark.asyncio
async def test_project_pages_include_generated_and_pinned_without_granting_access(client, db, route_env):
    db.html_artifacts = BrowseCollection()
    generated = artifacts.create(db, 'testuser', 'Generated', '<p>a</p>', 'one', {'project_uuid': 'p1'})
    pinned = artifacts.create(db, 'testuser', 'Pinned', '<p>b</p>', 'two')
    private = artifacts.create(db, 'other', 'Private', '<p>secret</p>', 'three', {'project_uuid': 'p1'})
    artifacts.create(db, 'testuser', 'Unrelated', '<p>c</p>', 'four')
    with patch.object(project_service, 'get_authorized_project', AsyncMock(return_value=SimpleNamespace(uuid='p1'))) as authorize, patch('app.models.project.ProjectPin.find', return_value=SimpleNamespace(to_list=AsyncMock(return_value=[SimpleNamespace(target_id=pinned['uuid']), SimpleNamespace(target_id=private['uuid'])]))):
        result = (await client.get('/api/pages/browse?project_uuid=p1')).json()
        assert {d['uuid'] for d in result['items']} == {generated['uuid'], pinned['uuid']}
        authorize.return_value = None
        assert (await client.get('/api/pages/browse?project_uuid=p1')).status_code == 404
        cookies, headers = _auth()
        response = await client.post('/api/pages', json={'title': 'Page', 'html': '<p>x</p>', 'request_id': 'denied', 'project_uuid': 'p1'}, cookies=cookies, headers=headers)
        assert response.status_code == 404
        assert len(db.html_artifacts.docs) == 4


@pytest.mark.asyncio
async def test_project_default_requires_edit_role_and_accessible_skill(client, route_env):
    project = SimpleNamespace(uuid='p1', default_skill_uuid='skill-1', set=AsyncMock())
    cookies, headers = _auth()
    with patch.object(project_service, 'get_authorized_project', AsyncMock(return_value=project)), patch.object(project_service, 'can_manage_project', AsyncMock(return_value=False)) as manage, patch.object(project_service, 'add_pin', AsyncMock()) as pin, patch('app.services.skill_service.snapshot_skill', AsyncMock(return_value=snapshot())) as read:
        response = await client.put('/api/projects/p1/default-skill', json={'skill_uuid': 'skill-1'}, cookies=cookies, headers=headers)
        assert response.status_code == 403
        read.assert_not_awaited()
        manage.return_value = True
        response = await client.put('/api/projects/p1/default-skill', json={'skill_uuid': 'skill-1'}, cookies=cookies, headers=headers)
        assert response.status_code == 200
        pin.assert_awaited_once_with(project, 'skill', 'skill-1', route_env.user)
        project.set.assert_awaited_with({'default_skill_uuid': 'skill-1'})
        assert (await client.get('/api/projects/p1/default-skill')).json()['active_skill']['version'] == 'pinned-v1'
        read.side_effect = HTTPException(404, 'Skill no longer accessible')
        assert (await client.get('/api/projects/p1/default-skill')).status_code == 404
        assert (await client.put('/api/projects/p1/default-skill', json={'skill_uuid': None}, cookies=cookies, headers=headers)).status_code == 200
        project.set.assert_awaited_with({'default_skill_uuid': None})


@pytest.mark.asyncio
async def test_new_resource_pins_reauthorize_before_mutating_and_hide_inaccessible_titles():
    project = SimpleNamespace(uuid='p1')
    user = SimpleNamespace(user_id='user')
    with patch.object(project_service, 'can_manage_project', AsyncMock(return_value=True)), patch.object(project_service, 'authorize_resource', AsyncMock(side_effect=HTTPException(404, 'Unavailable'))), patch.object(project_service, 'ProjectPin') as model:
        for kind in ['skill', 'artifact']:
            with pytest.raises(HTTPException):
                await project_service.add_pin(project, kind, 'private', user)
        model.assert_not_called()
        model.find.return_value.to_list = AsyncMock(return_value=[SimpleNamespace(pin_type='skill', target_id='private'), SimpleNamespace(pin_type='artifact', target_id='private')])
        assert await project_service.list_pins(project, user) == []


def test_page_edits_keep_origin_and_workflow_pages_keep_project(db):
    source = {'kind': 'chat', 'conversation_uuid': 'c1', 'project_uuid': 'p1'}
    doc = artifacts.create(db, 'testuser', 'Chat page', '<p>Original</p>', 'origin', source)
    changed = artifacts.revise(db, doc, 'Edited', '<p>Edited</p>', doc['latest_revision'])
    assert artifacts.metadata(changed, True)['source'] == source
    assert changed['project_uuid'] == 'p1'
    assert 'source' not in artifacts.metadata(changed, False)
    db.activity_event.docs.append({'workflow_session_id': 'run1', 'user_id': 'testuser', 'project_uuid': 'p1'})
    saved = artifacts.from_workflow(db, {'workflow': 'wf1', 'session_id': 'run1', 'status': 'completed', 'final_output': {'output': '<p>Result</p>'}}, 'testuser')
    assert saved['project_uuid'] == 'p1'
    assert saved['source']['session_id'] == 'run1'


@pytest.mark.asyncio
async def test_transcript_origin_requires_owned_chat_and_project_access(client, db, route_env):
    cookies, headers = _auth()
    payload = {'request_id': 'transcript', 'messages': [{'role': 'assistant', 'content': 'Reviewed'}],
               'project_uuid': 'p1', 'conversation_uuid': 'c1'}
    with patch.object(project_service, 'get_authorized_project', AsyncMock(return_value=SimpleNamespace(uuid='p1'))), patch('app.models.chat.ChatConversation.find_one', AsyncMock(return_value=None)) as conversation:
        response = await client.post('/api/pages/from-chat', json=payload, cookies=cookies, headers=headers)
        assert response.status_code == 404 and db.html_artifacts.docs == []
        conversation.assert_awaited_with({'uuid': 'c1', 'user_id': 'testuser'})
        conversation.return_value = SimpleNamespace(uuid='c1')
        response = await client.post('/api/pages/from-chat', json=payload, cookies=cookies, headers=headers)
        assert response.status_code == 200
        assert response.json()['source'] == {'kind': 'chat_export', 'conversation_uuid': 'c1', 'project_uuid': 'p1'}
        assert db.html_artifacts.docs[0]['project_uuid'] == 'p1'


@pytest.mark.asyncio
async def test_unpinning_clears_only_the_same_default():
    from unittest.mock import MagicMock
    project = SimpleNamespace(uuid='p1')
    collection = SimpleNamespace(update_one=AsyncMock())
    model = MagicMock()
    model.find.return_value.delete = AsyncMock()
    with patch.object(project_service, 'can_manage_project', AsyncMock(return_value=True)), patch.object(project_service, 'ProjectPin', model), patch.object(project_service.Project, 'get_motor_collection', return_value=collection):
        await project_service.remove_pin(project, 'skill', 's1', SimpleNamespace())
        collection.update_one.assert_awaited_once_with({'uuid': 'p1', 'default_skill_uuid': 's1'}, {'$set': {'default_skill_uuid': None}})
