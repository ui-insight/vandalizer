"""Usage drilldown must retain the same UTC interval and authorization scope."""
import datetime as dt
import os
from types import SimpleNamespace
from uuid import uuid4
from beanie import init_beanie
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import pytest_asyncio
from app.dependencies import get_current_user
from app.models.activity import ActivityEvent
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.routers import admin

pytestmark = pytest.mark.skipif(not os.environ.get('ADMIN_UX_TEST_MONGO_URL'), reason='Requires disposable MongoDB')

@pytest_asyncio.fixture
async def api():
    client = AsyncIOMotorClient(os.environ['ADMIN_UX_TEST_MONGO_URL'], serverSelectionTimeoutMS=3000)
    database = 'admin_window_test_' + uuid4().hex
    await init_beanie(database=client[database], document_models=[ActivityEvent, Team, TeamMembership, User])
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    actor = SimpleNamespace(user_id='window-admin', is_admin=True, is_staff=False, current_team=None)
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, actor
    finally:
        await client.drop_database(database)
        client.close()

@pytest.mark.asyncio
async def test_usage_failure_link_preserves_counts_and_stable_pages_for_global_and_team_admin(api):
    http, actor = api
    team = await Team(uuid='window-team', name='Window team', owner_user_id=actor.user_id).insert()
    await TeamMembership(team=team.id, user_id=actor.user_id, role='owner').insert()
    now = dt.datetime.now(dt.timezone.utc)
    def event(i, **fields):
        return ActivityEvent(type='workflow_run', status='failed', user_id=actor.user_id,
                             team_id=team.uuid if i % 2 else str(team.id), title=f'Window {i:03d}',
                             started_at=now - dt.timedelta(days=1), **fields)
    await ActivityEvent.insert_many([event(i) for i in range(53)])
    await ActivityEvent(type='workflow_run', status='failed', user_id='other', team_id='other-team', started_at=now - dt.timedelta(days=1)).insert()
    await ActivityEvent(type='workflow_run', status='completed', user_id=actor.user_id, team_id=team.uuid, started_at=now - dt.timedelta(days=1)).insert()
    await ActivityEvent(type='conversation', status='failed', user_id=actor.user_id, team_id=team.uuid, started_at=now - dt.timedelta(days=1)).insert()
    await ActivityEvent(type='workflow_run', status='failed', user_id=actor.user_id, team_id=team.uuid, started_at=now - dt.timedelta(days=40)).insert()
    await ActivityEvent(type='workflow_run', status='failed', user_id=actor.user_id, team_id=team.uuid, started_at=now + dt.timedelta(days=1)).insert()
    for scoped, expected in [(False, 54), (True, 53)]:
        actor.is_admin = not scoped
        actor.current_team = team.id
        stats = (await http.get('/admin/usage?days=7')).json()
        assert stats['workflows_failed'] == expected
        params = {'started_after': stats['period_start'], 'started_before': stats['period_end'], 'status': 'failed', 'per_page': 50}
        first = await http.get('/admin/workflows', params=params)
        second = await http.get('/admin/workflows', params={**params, 'page': 2})
        assert first.status_code == second.status_code == 200
        a, b = first.json(), second.json()
        assert a['total'] == b['total'] == expected
        assert a['summary']['failed'] == expected and a['summary']['completed'] == 1
        ids = [item['id'] for item in a['items'] + b['items']]
        assert len(set(ids)) == expected
        again = (await http.get('/admin/workflows', params=params)).json()
        assert [item['id'] for item in again['items']] == ids[:50]
        assert all(item['status'] == 'failed' for item in a['items'] + b['items'])
    actor.current_team = None
    assert (await http.get('/admin/workflows', params=params)).status_code == 403
    assert (await http.get('/admin/usage')).status_code == 403

@pytest.mark.asyncio
async def test_window_boundaries_offsets_and_validation(api):
    http, _ = api
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    for title, time in [('before', start-dt.timedelta(milliseconds=1)), ('start', start), ('last', end-dt.timedelta(milliseconds=1)), ('end', end)]:
        await ActivityEvent(type='workflow_run', status='failed', user_id='window-admin', title=title, started_at=time).insert()
    params = {'started_after': '2025-12-31T19:00:00-05:00', 'started_before': end.isoformat()}
    response = await http.get('/admin/workflows', params=params)
    assert response.status_code == 200
    assert [item['title'] for item in response.json()['items']] == ['last', 'start']
    assert response.json()['summary']['total'] == 2
    for before, after in [(start.isoformat(), end.isoformat()), (start.isoformat(), start.isoformat()), ('bad', start.isoformat())]:
        assert (await http.get('/admin/workflows', params={'started_before': before, 'started_after': after})).status_code == 422
    literal = await http.get('/admin/workflows', params={**params, 'search': '.*'})
    assert literal.json()['total'] == 0 and literal.json()['summary']['total'] == 0
