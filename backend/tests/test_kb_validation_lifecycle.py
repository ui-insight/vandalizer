import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.services import kb_validation_lifecycle as lifecycle

TASK = '00000000-0000-4000-8000-000000000001'
OPTIONS = {"mode": "judge", "skip_judge": False, "query_uuids": None}


def receipt(**overrides):
    return SimpleNamespace(uuid=TASK, kb_uuid='kb', user_id='user', options=OPTIONS,
        dispatch_uncertain=False, active=True, terminal_status=None, set=AsyncMock(), created_at=datetime.datetime.now(datetime.timezone.utc), **overrides)


@pytest.mark.asyncio
async def test_publish_once_and_repeated_request_reuses_receipt():
    model = MagicMock()
    model.return_value.uuid, model.return_value.options = TASK, OPTIONS
    model.return_value.insert = AsyncMock(side_effect=[None, DuplicateKeyError('duplicate')])
    model.find_one = AsyncMock(return_value=receipt())
    with patch.object(lifecycle, 'KBValidationTask', model), patch('app.tasks.kb_validation_tasks.validate_kb_task.apply_async') as publish:
        one = await lifecycle.start_validation('kb', 'user', OPTIONS, TASK)
        two = await lifecycle.start_validation('kb', 'user', OPTIONS, TASK)
    assert one == two == {'task_id': TASK, 'status': 'queued', 'options': OPTIONS, 'resumed': False}
    publish.assert_called_once_with(args=['kb', 'user', 'judge', False, None], task_id=TASK, retry=False)


@pytest.mark.asyncio
async def test_lost_publish_acknowledgement_is_not_republished():
    model = MagicMock()
    model.return_value.uuid, model.return_value.options = TASK, OPTIONS
    model.return_value.insert = AsyncMock(side_effect=[None, DuplicateKeyError('duplicate')])
    model.return_value.save = AsyncMock()
    model.find_one = AsyncMock(return_value=receipt())
    with patch.object(lifecycle, 'KBValidationTask', model), patch('app.tasks.kb_validation_tasks.validate_kb_task.apply_async', side_effect=ConnectionError('lost')) as publish:
        await lifecycle.start_validation('kb', 'user', OPTIONS, TASK)
        await lifecycle.start_validation('kb', 'user', OPTIONS, TASK)
    assert publish.call_count == 1
    assert model.return_value.dispatch_uncertain is True
    model.return_value.save.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('kb,user,options', [('other', 'user', OPTIONS), ('kb', 'other', OPTIONS), ('kb', 'user', {**OPTIONS, 'mode': 'judge+baseline'})])
async def test_existing_request_cannot_be_rebound(kb, user, options):
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=receipt())):
        with pytest.raises(HTTPException) as error:
            await lifecycle.existing_validation(kb, user, options, TASK)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_task_ownership_checked_before_backend_or_result_lookup():
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=None)) as find, patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock()) as saved, patch.object(lifecycle, 'AsyncResult') as backend:
        with pytest.raises(HTTPException) as error:
            await lifecycle.validation_status('kb', 'other-user', TASK)
    assert error.value.status_code == 404
    find.assert_awaited_once_with({'uuid': TASK, 'kb_uuid': 'kb', 'user_id': 'other-user'})
    saved.assert_not_called()
    backend.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('state,expected', [('PENDING','queued'), ('STARTED','running'), ('RETRY','retrying'), ('FAILURE','failed'), ('REVOKED','failed'), ('SUCCESS','unknown')])
async def test_worker_status_mapping(state, expected):
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=receipt())), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=None)), patch.object(lifecycle, 'AsyncResult', return_value=SimpleNamespace(state=state)):
        out = await lifecycle.validation_status('kb', 'user', TASK)
    assert out['status'] == expected
    assert out['delayed'] is False


@pytest.mark.asyncio
async def test_delayed_unknown_does_not_claim_worker_failure():
    item = receipt()
    item.created_at -= datetime.timedelta(days=2)
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=item)), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=None)), patch.object(lifecycle, 'AsyncResult', return_value=SimpleNamespace(state='PENDING')):
        out = await lifecycle.validation_status('kb', 'user', TASK)
    assert out['status'] == 'unknown'
    assert out['delayed'] is True


@pytest.mark.asyncio
async def test_persisted_exact_result_survives_celery_expiry_and_preserves_certified_score():
    result = SimpleNamespace(uuid='saved-run', result_snapshot={'validation_task_id': TASK, 'raw_score': 90}, score=72, score_breakdown={'final_score':72})
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=receipt())), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=result)) as find, patch.object(lifecycle, 'AsyncResult') as backend:
        out = await lifecycle.validation_status('kb', 'user', TASK)
    assert out['run_uuid'] == 'saved-run'
    assert out['status'] == 'completed'
    assert out['result']['score'] == 72
    assert find.call_args.args[0]['result_snapshot.validation_task_id'] == TASK
    backend.assert_not_called()


@pytest.mark.asyncio
async def test_status_route_checks_kb_access_before_task_lookup():
    from app.routers import knowledge
    with patch.object(knowledge.organization_service, 'get_user_org_ancestry', AsyncMock(return_value=[])), patch.object(knowledge.svc, 'get_knowledge_base', AsyncMock(return_value=None)), patch.object(lifecycle, 'validation_status', AsyncMock()) as status:
        with pytest.raises(HTTPException) as error:
            await knowledge.get_validation_task('kb', TASK, SimpleNamespace(user_id='user'))
    assert error.value.status_code == 404
    status.assert_not_called()


@pytest.mark.asyncio
async def test_start_route_recovers_receipt_even_if_selected_questions_were_deleted():
    from app.routers import knowledge
    request = SimpleNamespace(json=AsyncMock(return_value={'async': True, 'request_id': TASK, 'mode': 'judge', 'query_uuids':['deleted-question']}))
    response = {'task_id': TASK, 'status': 'queued'}
    with patch.object(knowledge.organization_service, 'get_user_org_ancestry', AsyncMock(return_value=[])), patch.object(knowledge.svc, 'get_knowledge_base', AsyncMock(return_value=SimpleNamespace(uuid='kb'))), patch.object(lifecycle, 'existing_validation', AsyncMock(return_value=response)), patch('app.models.kb_test_query.KBTestQuery.find') as queries:
        assert await knowledge.validate_knowledge_base('kb', request, SimpleNamespace(user_id='user')) == response
    queries.assert_not_called()


@pytest.mark.asyncio
async def test_worker_retry_does_not_repeat_an_already_persisted_check():
    from app.tasks.kb_validation_tasks import _validate_kb_async
    with patch('app.database.init_db', AsyncMock()), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=SimpleNamespace(uuid='saved'))) as saved, patch('app.services.kb_validation_service.run_kb_validation', AsyncMock()) as run:
        result = await _validate_kb_async('kb', 'user', 'judge', False, None, TASK)
    assert result['already_completed'] is True
    run.assert_not_called()
    assert saved.call_args.args[0]['result_snapshot.validation_task_id'] == TASK


@pytest.mark.asyncio
async def test_worker_threads_task_identity_into_persisted_result():
    from app.tasks.kb_validation_tasks import _validate_kb_async
    with patch('app.database.init_db', AsyncMock()), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=None)), patch('app.services.kb_validation_service.run_kb_validation', AsyncMock(return_value={'raw_score':75})) as run:
        await _validate_kb_async('kb', 'user', 'judge', False, ['q1'], TASK)
    assert run.call_args.kwargs['validation_task_id'] == TASK


@pytest.mark.asyncio
async def test_competing_window_resumes_the_active_check_without_dispatch():
    active = receipt()
    model = MagicMock()
    model.return_value.insert = AsyncMock(side_effect=DuplicateKeyError('active lock'))
    model.find_one = AsyncMock(side_effect=[None, active])
    with patch.object(lifecycle, 'KBValidationTask', model), patch('app.tasks.kb_validation_tasks.validate_kb_task.apply_async') as publish:
        out = await lifecycle.start_validation('kb', 'user', {**OPTIONS, 'mode': 'judge+baseline'}, '00000000-0000-4000-8000-000000000002')
    assert out['task_id'] == TASK
    assert out['options'] == OPTIONS
    assert out['resumed'] is True
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_restores_most_recent_outcome_if_nothing_is_active():
    model = MagicMock()
    model.find_one = AsyncMock(return_value=None)
    model.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[receipt()])
    with patch.object(lifecycle, 'KBValidationTask', model), patch.object(lifecycle, 'validation_status', AsyncMock(return_value={'task_id': TASK, 'status': 'failed'})):
        out = await lifecycle.active_validation('kb', 'user')
    assert out['task']['status'] == 'failed'
    assert out['task']['options'] == OPTIONS
    model.find.assert_called_once_with({'kb_uuid': 'kb', 'user_id': 'user'})


@pytest.mark.asyncio
async def test_confirmed_failure_releases_active_lock_and_survives_result_expiry():
    item = receipt()
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=item)), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=None)), patch.object(lifecycle, 'AsyncResult', return_value=SimpleNamespace(state='FAILURE')):
        assert (await lifecycle.validation_status('kb', 'user', TASK))['status'] == 'failed'
    item.set.assert_awaited_once_with({'active': False, 'terminal_status': 'failed'})
    item.active = False
    item.terminal_status = 'failed'
    with patch.object(lifecycle.KBValidationTask, 'find_one', AsyncMock(return_value=item)), patch.object(lifecycle.ValidationRun, 'find_one', AsyncMock(return_value=None)), patch.object(lifecycle, 'AsyncResult') as backend:
        assert (await lifecycle.validation_status('kb', 'user', TASK))['status'] == 'failed'
    backend.assert_not_called()
