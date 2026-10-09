"""Disposable-database HTTP checks for the admin UX fixes; no external delivery."""
import os
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.models.team import Team, TeamMembership, TeamInvite, TeamJoinLink
from app.models.user import User
from app.models.knowledge import KnowledgeBase
from app.models.certification import CertificationProgress, CertificationEnrollment, CertificationEnrollmentSelection
from app.models.system_config import SystemConfig
from app.routers import admin
from app.dependencies import get_current_user

pytestmark = pytest.mark.skipif(not os.environ.get('ADMIN_UX_TEST_MONGO_URL'), reason='Requires an explicitly configured disposable MongoDB test connection')

@pytest_asyncio.fixture
async def api(monkeypatch):
    client = AsyncIOMotorClient(os.environ['ADMIN_UX_TEST_MONGO_URL'], serverSelectionTimeoutMS=3000)
    name = 'admin_ux_test_' + uuid4().hex
    await init_beanie(database=client[name], document_models=[Team, TeamMembership, TeamInvite, TeamJoinLink, User, SystemConfig, KnowledgeBase, CertificationProgress, CertificationEnrollment, CertificationEnrollmentSelection])
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    actor = SimpleNamespace(user_id='qa-admin', is_admin=True, is_staff=False)
    app.dependency_overrides[get_current_user] = lambda: actor
    monkeypatch.setattr(admin, '_audit', AsyncMock())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, actor
    finally:
        await client.drop_database(name)
        client.close()

@pytest.mark.asyncio
async def test_processing_and_policy_saves_persist_independently_and_reject_bad_numbers(api):
    http, actor = api
    cfg = await SystemConfig.get_config()
    cfg.compliance_config = {'enabled': False, 'chunk_size': 8000, 'chunk_overlap': 200}
    await cfg.save()
    quality = {'quality_tiers': {'excellent': {'min_score': 95}, 'good': {'min_score': 75}, 'fair': {'min_score': 55}}}
    response = await http.put('/admin/config', json={'quality_config': quality})
    assert response.status_code == 200, response.text
    saved = await SystemConfig.get_config()
    assert saved.quality_config == quality and not saved.compliance_config['enabled']
    for body in ({'quality_config': {'quality_tiers': {'excellent': {'min_score': 150}}}}, {'retention_config': {'activity_retention_days': -1}}):
        rejected = await http.put('/admin/config', json=body)
        assert rejected.status_code == 422, rejected.text
    rejected = await http.put('/admin/config/compliance', json={'chunk_size': 500, 'chunk_overlap': 500})
    assert rejected.status_code == 422
    accepted = await http.put('/admin/config/compliance', json={'enabled': True, 'chunk_size': 500, 'chunk_overlap': 100})
    assert accepted.status_code == 200, accepted.text
    saved = await SystemConfig.get_config()
    assert saved.compliance_config['enabled'] and saved.quality_config == quality
    actor.is_admin = False
    denied = await http.put('/admin/config', json={'quality_config': quality})
    assert denied.status_code == 403

@pytest.mark.asyncio
async def test_management_team_inventory_pages_past_500_and_searches_all_records(api):
    http, actor = api
    await Team.insert_many([Team(uuid=f'team-{i}', name=f'Team {i:04d}', owner_user_id='qa-admin') for i in range(503)])
    last = await Team.find_one({'uuid': 'team-502'})
    await TeamMembership(team=last.id, user_id='qa-admin', role='owner').insert()
    first = await http.get('/admin/teams/all?limit=500')
    last_page = await http.get('/admin/teams/all?limit=500&offset=500')
    assert first.status_code == last_page.status_code == 200
    a, b = first.json(), last_page.json()
    assert a['total'] == b['total'] == 503 and a['capped'] and not b['capped']
    assert len({row['uuid'] for row in a['items'] + b['items']}) == 503
    assert b['items'][-1]['member_count'] == 1
    search = await http.get('/admin/teams/all?q=0502')
    assert [row['uuid'] for row in search.json()['items']] == ['team-502']
    actor.is_admin = False
    denied = await http.get('/admin/teams/all')
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_certification_and_knowledge_inventory_reach_late_records(api):
    http, _ = api
    await CertificationProgress.insert_many([CertificationProgress(user_id=f'learner-{i:04d}') for i in range(503)])
    last = await http.get('/admin/certifications?offset=500&limit=100')
    assert last.status_code == 200, last.text
    assert [row['user_id'] for row in last.json()['items']] == ['learner-0500', 'learner-0501', 'learner-0502']
    search = await http.get('/admin/certifications?q=0502')
    assert search.status_code == 200 and search.json()['total'] == 1
    assert await CertificationProgress.find().count() == 503  # Listing never changes enrollment/progress.
    await KnowledgeBase.insert_many([KnowledgeBase(uuid=f'kb-{i}', title=f'Research {i:04d}', user_id='qa-admin') for i in range(503)])
    page = await http.get('/admin/knowledge-bases?limit=500&offset=500')
    assert page.status_code == 200, page.text
    assert page.json()['total'] == 503 and len(page.json()['knowledge_bases']) == 3


@pytest.mark.asyncio
async def test_disposable_membership_ownership_and_join_link_lifecycle(api):
    import datetime
    from app.services import team_service as service
    owner = await User(user_id='qa-owner', name='QA Owner').insert()
    member = await User(user_id='qa-member', name='QA Member').insert()
    outsider = await User(user_id='qa-outsider').insert()
    team = await service.create_team('Disposable team — lifecycle QA', owner.user_id)
    owner.current_team = team.id
    await owner.save()
    link = await service.create_join_link(team.uuid, owner.user_id, max_uses=2)
    await service.accept_join_link(link.token, member)
    await service.accept_join_link(link.token, member)
    assert await TeamMembership.find({'team': team.id, 'user_id': member.user_id}).count() == 1
    assert (await TeamJoinLink.get(link.id)).use_count == 1
    with pytest.raises(ValueError, match='owner'):
        await service.delete_team(team.uuid, member.user_id)
    with pytest.raises(ValueError, match='Owners cannot leave'):
        await service.remove_member(team.uuid, owner.user_id, owner.user_id)
    await service.transfer_ownership(team.uuid, owner.user_id, member.user_id)
    assert (await Team.get(team.id)).owner_user_id == member.user_id
    assert (await TeamMembership.find_one({'team': team.id, 'user_id': owner.user_id})).role == 'admin'
    await service.remove_member(team.uuid, owner.user_id, owner.user_id)
    assert (await User.get(owner.id)).current_team != team.id
    await service.revoke_join_link(link.token, member.user_id)
    with pytest.raises(ValueError, match='revoked'):
        await service.accept_join_link(link.token, outsider)
    expired = await service.create_join_link(team.uuid, member.user_id)
    expired.expires_at = datetime.datetime.now() - datetime.timedelta(seconds=1)
    await expired.save()
    with pytest.raises(ValueError, match='expired'):
        await service.accept_join_link(expired.token, outsider)
    await TeamMembership(team=team.id, user_id=outsider.user_id).insert()
    await service.remove_member(team.uuid, outsider.user_id, member.user_id)
    assert await TeamMembership.find({'team': team.id, 'user_id': outsider.user_id}).count() == 0
    await service.delete_team(team.uuid, member.user_id)
    assert await Team.get(team.id) is None
    assert await TeamMembership.find({'team': team.id}).count() == 0
    assert (await User.get(member.id)).current_team is None
