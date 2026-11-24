"""Full-inventory search against disposable MongoDB, including owner/team joins."""
import datetime
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from beanie import init_beanie
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.dependencies import get_current_user
from app.models.knowledge import KnowledgeBase
from app.models.team import Team
from app.models.user import User
from app.routers import admin

pytestmark = pytest.mark.skipif(not os.environ.get('ADMIN_UX_TEST_MONGO_URL'), reason='Requires an explicitly configured disposable MongoDB connection')


@pytest_asyncio.fixture
async def inventory():
    mongo = AsyncIOMotorClient(os.environ['ADMIN_UX_TEST_MONGO_URL'], serverSelectionTimeoutMS=3000)
    name = 'admin_kb_search_test_' + uuid4().hex
    await init_beanie(database=mongo[name], document_models=[KnowledgeBase, Team, User])
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    actor = SimpleNamespace(user_id='admin', is_admin=True, is_staff=False)
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            yield client, actor
    finally:
        await mongo.drop_database(name)
        mongo.close()


@pytest.mark.asyncio
async def test_search_finds_every_field_beyond_initial_page_and_filters_before_paging(inventory):
    http, actor = inventory
    await User(user_id='late-owner', email='late.owner@example.test').insert()
    await Team(uuid='late-team', name='Regional research', owner_user_id='late-owner').insert()
    now = datetime.datetime.now(datetime.timezone.utc)
    await KnowledgeBase.insert_many([
        KnowledgeBase(uuid=f'kb-{i}', title=f'Policy {i:04d}', user_id='ordinary', status='ready', updated_at=now)
        for i in range(503)
    ])
    target = await KnowledgeBase.find_one({'uuid': 'kb-502'})
    target.user_id = 'late-owner'
    target.team_id = 'late-team'
    target.tags = ['v2026.10']
    target.status = 'error'
    target.updated_at = now + datetime.timedelta(days=1)
    await target.save()
    first = await http.get('/admin/knowledge-bases', params={'limit': 100, 'sort': 'title'})
    assert first.status_code == 200, first.text
    assert first.json()['total'] == 503
    assert 'kb-502' not in [r['uuid'] for r in first.json()['knowledge_bases']]
    for query in ['POLICY 0502', 'LATE.OWNER@', 'regional research', 'v2026.10']:
        response = await http.get('/admin/knowledge-bases', params={'search': query, 'limit': 100, 'status': 'error', 'sort': 'title'})
        assert response.status_code == 200, response.text
        assert response.json()['total'] == 1
        assert [row['uuid'] for row in response.json()['knowledge_bases']] == ['kb-502']
        assert response.json()['knowledge_bases'][0]['owner_email'] == 'late.owner@example.test'
        assert response.json()['knowledge_bases'][0]['team_name'] == 'Regional research'
    no_match = await http.get('/admin/knowledge-bases', params={'search': 'v2026.*'})
    assert no_match.json() == {'total': 0, 'knowledge_bases': []}
    ready = await http.get('/admin/knowledge-bases', params={'status': 'ready', 'offset': 500, 'limit': 100, 'sort': 'title'})
    assert ready.json()['total'] == 502 and len(ready.json()['knowledge_bases']) == 2
    newest = await http.get('/admin/knowledge-bases', params={'sort': 'updated', 'limit': 1})
    assert newest.json()['knowledge_bases'][0]['uuid'] == 'kb-502'
    actor.is_admin = False
    actor.is_staff = True
    assert (await http.get('/admin/knowledge-bases', params={'search': 'regional'})).status_code == 200
    actor.is_staff = False
    assert (await http.get('/admin/knowledge-bases')).status_code == 403
    assert await KnowledgeBase.find().count() == 503


@pytest.mark.asyncio
async def test_title_order_is_case_insensitive_and_pages_with_ties_are_stable(inventory):
    http, _ = inventory
    await KnowledgeBase.insert_many([KnowledgeBase(uuid=f'kb-{i}', title=title, user_id='missing-owner', team_id='missing-team') for i, title in enumerate(['Beta', 'alpha', 'ALPHA', 'zebra'])])
    rows = []
    for offset in [0, 2]:
        response = await http.get('/admin/knowledge-bases', params={'sort': 'title', 'limit': 2, 'offset': offset})
        assert response.status_code == 200, response.text
        assert response.json()['total'] == 4
        rows.extend(response.json()['knowledge_bases'])
    assert [row['title'].lower() for row in rows] == ['alpha', 'alpha', 'beta', 'zebra']
    assert len({row['uuid'] for row in rows}) == 4
    response = await http.get('/admin/knowledge-bases', params={'search': 'alpha'})
    assert response.json()['total'] == 2  # Missing related owners/teams do not hide title matches.
    assert all(row['owner_email'] is None for row in response.json()['knowledge_bases'])
    beyond = await http.get('/admin/knowledge-bases', params={'offset': 999})
    assert beyond.json() == {'total': 4, 'knowledge_bases': []}


@pytest.mark.asyncio
async def test_rejects_invalid_filter_and_paging_parameters(inventory):
    http, _ = inventory
    for params in [{'sort': 'other'}, {'status': 'other'}, {'offset': -1}, {'limit': 0}, {'search': 'a' * 301}]:
        response = await http.get('/admin/knowledge-bases', params=params)
        assert response.status_code == 422, response.text
