"""Legacy thresholds cannot use currently inaccessible extraction fields."""
import asyncio
from uuid import uuid4

import pytest

from app.models.search_set import SearchSet, SearchSetItem
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.models.team import Team, TeamMembership
from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
from app.models.certification import CertificationProgress
from app.services import certification_service
from app.services.certification_versions import grading
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


async def field_fixture(repo, route):
    learner = await repo.ensure_initial('legacy-field-learner')
    artifact = await SearchSet(uuid=uuid4().hex, title='Private extraction', status='active',
        set_type='extraction', user_id='another-owner',
        created_by_user_id=learner.user_id if route == 'creator' else None).insert()
    for i in range(15):
        await SearchSetItem(searchset=artifact.uuid, user_id=artifact.user_id,
            searchphrase=f'Private field {i}', title=f'Private field {i}', searchtype='extraction').insert()
    if route == 'linked':
        task = await WorkflowStepTask(name='Extraction', data={'search_set_uuid': artifact.uuid}).insert()
        step = await WorkflowStep(name='Extract', tasks=[task.id]).insert()
        await Workflow(name='My workflow', user_id=learner.user_id, steps=[step.id]).insert()
    return learner, artifact


async def grade_fields(repo, learner, versioned, monkeypatch):
    if versioned:
        return await grading.grade(repo.catalog.load(learner.course_version),
            await repo.read_progress(learner.user_id, learner.uuid), 'extraction_engine')
    monkeypatch.setattr(certification_service, 'current_operation', lambda: None)
    return await certification_service.validate_module.__wrapped__(learner.user_id, 'extraction_engine')


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('route', ['linked', 'creator'])
async def test_inaccessible_extraction_fields_cannot_pass_legacy_grading(repo, monkeypatch, versioned, route):
    learner, _ = await field_fixture(repo, route)
    result = await grade_fields(repo, learner, versioned, monkeypatch)
    assert result['passed'] is False
    assert result['stars'] == 0
    assert '0 unique fields' in result['checks'][0]['detail']
    assert (await repo.read_progress(learner.user_id, learner.uuid)).total_xp == 0


async def grant_access(learner, artifact, grant):
    membership = None
    if grant == 'owner':
        artifact.user_id = learner.user_id
    elif grant == 'global':
        artifact.is_global = True
    elif grant == 'team':
        team = await Team(uuid=uuid4().hex, name='Training team', owner_user_id='another-owner').insert()
        membership = await TeamMembership(team=team.id, user_id=learner.user_id).insert()
        artifact.team_id = team.uuid
    elif grant == 'library':
        item = await LibraryItem(kind=LibraryItemKind.SEARCH_SET, item_id=artifact.id,
                                 added_by_user_id=learner.user_id).insert()
        await Library(title='My accessible library', scope=LibraryScope.PERSONAL,
                      owner_user_id=learner.user_id, items=[item.id]).insert()
    await artifact.save()
    return membership


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('route', ['linked', 'creator'])
@pytest.mark.parametrize('grant', ['owner', 'global', 'team', 'library'])
async def test_legacy_permitted_fields_keep_the_original_thresholds(repo, monkeypatch, versioned, route, grant):
    learner, artifact = await field_fixture(repo, route)
    await grant_access(learner, artifact, grant)
    result = await grade_fields(repo, learner, versioned, monkeypatch)
    assert result['passed'] is True
    assert result['stars'] == 1
    assert '15 unique fields' in result['checks'][0]['detail']


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('route', ['linked', 'creator'])
async def test_legacy_grading_rechecks_revoked_team_access(repo, monkeypatch, versioned, route):
    learner, artifact = await field_fixture(repo, route)
    membership = await grant_access(learner, artifact, 'team')
    assert (await grade_fields(repo, learner, versioned, monkeypatch))['passed'] is True
    await membership.delete()
    result = await grade_fields(repo, learner, versioned, monkeypatch)
    assert result['passed'] is False
    assert '0 unique fields' in result['checks'][0]['detail']


@pytest.mark.parametrize('versioned', [False, True])
async def test_inaccessible_link_does_not_discard_the_learners_inline_fields(repo, monkeypatch, versioned):
    learner, _ = await field_fixture(repo, 'linked')
    task = await WorkflowStepTask.find_one({'name': 'Extraction'})
    task.data['keys'] = [f'My inline field {i}' for i in range(20)]
    await task.save()
    result = await grade_fields(repo, learner, versioned, monkeypatch)
    assert result['passed'] is True and result['stars'] == 2
    assert '20 unique fields' in result['checks'][0]['detail']


@pytest.mark.parametrize('versioned', [False, True])
async def test_concurrent_legacy_reads_keep_each_learners_access(repo, monkeypatch, versioned):
    from app.services.certification_versions import legacy_access
    learner, artifact = await field_fixture(repo, 'creator')
    owner = await repo.ensure_initial(artifact.user_id)
    real_authorize = legacy_access.get_authorized_search_set
    arrived, overlap = set(), asyncio.Event()

    async def authorize(reference, user):
        arrived.add(user.user_id)
        if len(arrived) == 2:
            overlap.set()
        await asyncio.wait_for(overlap.wait(), timeout=5)
        return await real_authorize(reference, user)

    monkeypatch.setattr(legacy_access, 'get_authorized_search_set', authorize)
    denied, allowed = await asyncio.gather(
        grade_fields(repo, learner, versioned, monkeypatch),
        grade_fields(repo, owner, versioned, monkeypatch))
    assert denied['passed'] is False and allowed['passed'] is True
    assert '0 unique fields' in denied['checks'][0]['detail']
    assert '15 unique fields' in allowed['checks'][0]['detail']


@pytest.mark.parametrize('versioned', [False, True])
async def test_revocation_during_field_read_does_not_supply_legacy_credit(repo, monkeypatch, versioned):
    learner, artifact = await field_fixture(repo, 'creator')
    membership = await grant_access(learner, artifact, 'team')
    find = SearchSetItem.find

    class RevokingQuery:
        def __init__(self, query):
            self.query = query

        async def to_list(self, *args, **kwargs):
            records = await self.query.to_list(*args, **kwargs)
            await membership.delete()
            return records

    monkeypatch.setattr(SearchSetItem, 'find', lambda *args, **kwargs: RevokingQuery(find(*args, **kwargs)))
    result = await grade_fields(repo, learner, versioned, monkeypatch)
    assert result['passed'] is False
    assert '0 unique fields' in result['checks'][0]['detail']


@pytest.mark.parametrize('versioned', [False, True])
async def test_refused_new_legacy_completion_preserves_earlier_earned_credit(versioned_runtime, monkeypatch, versioned):
    from app.services.certification_versions import runtime
    learner, _ = await field_fixture(versioned_runtime, 'creator')
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    collection = CertificationProgress.get_motor_collection()
    await collection.update_one({'user_id': learner.user_id}, {'$set': {
        'total_xp': 225, 'modules.extraction_engine': {
            'completed': True, 'stars': 3, 'completed_at': '2026-09-01T12:00:00Z', 'attempts': 1}}})
    if not versioned:
        await collection.update_one({'user_id': learner.user_id},
                                    {'$unset': {'enrollment_id': '', 'course_version': ''}})
    before = await collection.find_one({'user_id': learner.user_id})
    result = await certification_service.complete_module(
        learner.user_id, 'extraction_engine', enrollment_id=learner.uuid if versioned else None,
        request_id=uuid4().hex if versioned else None)
    assert result['error'] == 'Validation did not pass'
    assert result['validation']['passed'] is False
    after = await collection.find_one({'user_id': learner.user_id})
    for record in (before, after):
        record.pop('_certification_write_fence', None)
    assert after == before
