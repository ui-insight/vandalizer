"""Revoke actual paused selection workers; never take over grading or jobs."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from uuid import uuid4

from bson import ObjectId
import pytest

from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.selection_preparation_recovery import SelectionPreparationRecovery
from app.services.certification_versions.writes import save_progress
from tests.integration import test_certification_saved_course_selection as saved
from tests.integration import test_certification_upgrade_activation as activation

repo = activation.repo
pytestmark = activation.pytestmark


@asynccontextmanager
async def worker(repo, monkeypatch, *, kind='upgrade', phase='intent'):
    if kind == 'upgrade':
        source, request, journal, _ = await activation.setup(repo, certified=True)
        action = journal.activate
    else:
        source, _, _, request, journal, _ = await saved.setup(repo, earned=True)
        action = journal.select
    active = await repo.current(source.user_id)
    reached, release = asyncio.Event(), asyncio.Event()
    if phase == 'intent':
        owner, method = journal, 'commit'
        original = journal.commit
        async def pause(*args, **kwargs):
            reached.set()
            await release.wait()
            return await original(*args, **kwargs)
    elif phase == 'before_cas':
        owner, method = repo.selections, 'find_one_and_update'
        original = owner.find_one_and_update
        async def pause(query, update, **kwargs):
            if 'last_transition' in update.get('$set', {}):
                reached.set()
                await release.wait()
            return await original(query, update, **kwargs)
    else:
        owner, method = repo.progress, 'update_one'
        original = owner.update_one
        async def pause(query, update, **kwargs):
            if (query.get('_id') == ObjectId(active.progress_id)
                    and '_certification_write_fence' in update.get('$set', {}) and not reached.is_set()):
                reached.set()
                await release.wait()
            return await original(query, update, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(owner, method, pause)
        task = asyncio.create_task(action(source.user_id, request))
        try:
            await asyncio.wait_for(reached.wait(), timeout=15)
            yield source.user_id, active, request, journal, action, task, release
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


async def reviewed(service, user_id):
    preview = await service.preview(user_id)
    return {'request_id': uuid4().hex, 'preview_sha256': preview['preview_sha256'],
            'consent': 'stop_uncommitted_course_preparation_preserving_all_work'}


@pytest.mark.parametrize('kind', ['upgrade', 'return'])
@pytest.mark.parametrize('phase', ['before_acquisition', 'intent', 'before_cas'])
async def test_fenced_late_worker_cannot_switch_or_write_and_original_choice_can_retry(repo, monkeypatch, kind, phase):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch, kind=kind, phase=phase) as (user, current, request, journal, action, task, release):
        history = await saved.histories(repo, user)
        selection = await repo.selections.find_one({'user_id': user})
        body = await reviewed(service, user)
        assert await repo.selections.find_one({'user_id': user}) == selection
        assert await saved.histories(repo, user) == history
        result = await service.recover(user, body)
        assert result['status'] == 'preparation_stopped'
        assert result['selection_changed'] is result['credit_changed'] is result['assessments_repeated'] is False
        assert result['original_request_id'] == request['request_id']
        assert (await repo.current(user)).uuid == current.uuid
        assert await saved.histories(repo, user) == history
        # Start a new ordinary write before the old task unwinds. Its stale
        # acquisition/commit/finally must neither change nor unlock this worker.
        async with repo.write_boundary(user, current.uuid) as progress:
            now = await repo.selections.find_one({'user_id': user})
            release.set()
            outcome = (await asyncio.gather(task, return_exceptions=True))[0]
            assert isinstance(outcome, EnrollmentConflict), outcome
            assert await repo.selections.find_one({'user_id': user}) == now
            await save_progress(progress)
        assert await service.recover(user, body) == result
    selected = await action(user, request)
    assert selected['source_enrollment_id'] == current.uuid
    assert selected['revision'] == selection['revision'] + 1
    after = await saved.histories(repo, user)
    # Preparation may insert the missing blank target after a pre-acquisition
    # interruption; all previously existing histories remain identical.
    for key, values in history.items():
        if key == 'enrollments' and kind == 'upgrade':
            values = [{**value, 'state': 'active'} if value['uuid'] == selected['target_enrollment_id'] else value for value in values]
        assert all(value in after[key] for value in values)


@pytest.mark.parametrize('phase', ['intent_insert', 'claimed', 'fenced', 'journal_written', 'cleanup'])
async def test_recovery_itself_restarts_without_releasing_an_unfenced_worker(repo, monkeypatch, phase):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        if phase == 'intent_insert':
            owner, method = service.records, 'insert_one'
            original = owner.insert_one
            async def fail(*args, **kwargs):
                await original(*args, **kwargs)
                raise RuntimeError('Interrupted recovery')
        elif phase == 'claimed':
            owner, method = service, 'finish'
            async def fail(*args, **kwargs):
                raise RuntimeError('Interrupted recovery')
        elif phase == 'fenced':
            owner, method = repo.progress, 'update_one'
            original = owner.update_one
            async def fail(*args, **kwargs):
                await original(*args, **kwargs)
                raise RuntimeError('Interrupted recovery')
        elif phase == 'journal_written':
            owner, method = service.records, 'update_one'
            original = owner.update_one
            async def fail(*args, **kwargs):
                await original(*args, **kwargs)
                raise RuntimeError('Interrupted recovery')
        else:
            owner, method = service, 'clear'
            async def fail(*args, **kwargs):
                raise RuntimeError('Interrupted recovery')
        with monkeypatch.context() as patch:
            patch.setattr(owner, method, fail)
            with pytest.raises(RuntimeError, match='Interrupted recovery'):
                await service.recover(user, body)
        with pytest.raises(EnrollmentConflict):
            async with repo.write_boundary(user, current.uuid):
                pytest.fail('Unconfirmed recovery must keep the course locked')
        result = await SelectionPreparationRecovery(repo).recover(user, body)
        assert result['status'] == 'preparation_stopped'
        assert await service.recover(user, body) == result
        release.set()
        assert isinstance((await asyncio.gather(task, return_exceptions=True))[0], EnrollmentConflict)
        assert (await repo.current(user)).uuid == current.uuid
        assert await service.records.count_documents({'user_id': user}) == 1


@pytest.mark.parametrize('operation', ['complete_module', 'assess_practical', 'revalidate_upgrade_choice', 'certification_write'])
async def test_other_live_operations_cannot_be_stopped_by_selection_recovery(repo, operation):
    source = await repo.ensure_initial('protected-worker')
    service = SelectionPreparationRecovery(repo)
    async with repo.write_boundary(source.user_id, source.uuid, operation=operation):
        before = await repo.selections.find_one({'user_id': source.user_id})
        with pytest.raises(EnrollmentConflict):
            await service.preview(source.user_id)
        with pytest.raises(EnrollmentConflict):
            await service.recover(source.user_id, {'request_id': uuid4().hex, 'preview_sha256': '0' * 64,
                'consent': 'stop_uncommitted_course_preparation_preserving_all_work'})
        assert await repo.selections.find_one({'user_id': source.user_id}) == before


async def test_foreign_rebound_stale_and_corrupt_requests_cannot_release_a_worker(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        with pytest.raises(EnrollmentConflict):
            await service.recover('foreign', body)
        with pytest.raises(EnrollmentConflict):
            await service.recover(user, {**body, 'preview_sha256': 'f' * 64})
        original = service.finish
        async def fail(*args):
            raise RuntimeError('Paused recovery')
        with monkeypatch.context() as patch:
            patch.setattr(service, 'finish', fail)
            with pytest.raises(RuntimeError):
                await service.recover(user, body)
        with pytest.raises(EnrollmentConflict):
            await service.recover('foreign', body)
        with pytest.raises(EnrollmentConflict):
            await service.recover(user, {**body, 'preview_sha256': 'f' * 64})
        raw = await service.records.find_one({'uuid': body['request_id']})
        before = deepcopy(await repo.selections.find_one({'user_id': user}))
        await service.records.update_one({'uuid': raw['uuid']}, {'$set': {'record_sha256': '0' * 64}})
        with pytest.raises(CourseCatalogError):
            await service.recover(user, body)
        assert await repo.selections.find_one({'user_id': user}) == before
        await service.records.replace_one({'uuid': raw['uuid']}, raw)
        await original(raw, service.decode(raw))


async def test_if_original_selection_wins_recovery_cannot_revert_it(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        insert = service.records.insert_one
        async def original_wins(seed):
            result = await insert(seed)
            release.set()
            await task
            return result
        monkeypatch.setattr(service.records, 'insert_one', original_wins)
        with pytest.raises(EnrollmentConflict):
            await service.recover(user, body)
        selected = await task
        assert (await repo.current(user)).uuid == selected['target_enrollment_id']
        assert (await repo.selections.find_one({'user_id': user}))['in_flight_writes'] == 0


async def test_old_recovery_replay_cannot_release_a_later_worker(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        result = await service.recover(user, body)
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    async with repo.write_boundary(user, current.uuid):
        before = await repo.selections.find_one({'user_id': user})
        assert await service.recover(user, body) == result
        assert await repo.selections.find_one({'user_id': user}) == before


async def test_rehashed_recovery_cannot_substitute_another_owned_progress_record(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        async def fail(*args):
            raise RuntimeError('Paused before fencing')
        with monkeypatch.context() as patch:
            patch.setattr(service, 'finish', fail)
            with pytest.raises(RuntimeError):
                await service.recover(user, body)
        original = await service.records.find_one({'uuid': body['request_id']})
        intent = service.decode(original)
        target = await repo.progress.find_one({'user_id': user, '_id': {'$ne': ObjectId(current.progress_id)}})
        intent['snapshot']['progress_id'] = str(target['_id'])
        digest = encode(intent['snapshot'])[1]
        intent['request']['preview_sha256'] = digest
        payload, record_digest = encode(intent)
        await service.records.update_one({'uuid': original['uuid']}, {'$set': {'record_json': payload, 'record_sha256': record_digest}})
        with pytest.raises(CourseCatalogError, match='original source'):
            await service.recover(user, {**body, 'preview_sha256': digest})
        assert await repo.progress.find_one({'_id': target['_id']}) == target
        await service.records.replace_one({'uuid': original['uuid']}, original)
        await service.recover(user, body)


async def test_changed_fence_after_recovery_claim_is_never_released(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        original_finish = service.finish
        async def changed(raw, intent):
            await repo.progress.update_one({'_id': ObjectId(current.progress_id)}, {'$set': {'_certification_write_fence': 'unrelated-fence'}})
            return await original_finish(raw, intent)
        monkeypatch.setattr(service, 'finish', changed)
        with pytest.raises(EnrollmentConflict, match='fence changed'):
            await service.recover(user, body)
        selected = await repo.selections.find_one({'user_id': user})
        assert selected['in_flight_writes'] == 1 and selected['active_write']['id'] == body['request_id']
        assert (await service.records.find_one({'uuid': body['request_id']}))['state'] == 'prepared'


async def test_concurrent_recovery_requests_cannot_release_two_different_workers(repo, monkeypatch):
    service = SelectionPreparationRecovery(repo)
    async with worker(repo, monkeypatch) as (user, current, request, journal, action, task, release):
        body = await reviewed(service, user)
        bodies = [body, {**body, 'request_id': uuid4().hex}]
        results = await asyncio.gather(*(SelectionPreparationRecovery(repo).recover(user, item) for item in bodies), return_exceptions=True)
        assert sum(isinstance(item, dict) for item in results) == 1
        assert all(isinstance(item, (dict, EnrollmentConflict)) for item in results)
        selected = await repo.selections.find_one({'user_id': user})
        assert selected['active_enrollment_id'] == current.uuid and selected['in_flight_writes'] == 0
