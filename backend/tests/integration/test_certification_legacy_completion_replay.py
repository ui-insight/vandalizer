"""Identified legacy completion retries return their original saved result."""
import asyncio
from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import certification_service as service
from app.services.certification_versions import runtime
from app.services.certification_versions import legacy_completions as journal
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.catalog import CourseCatalogError
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


async def test_legacy_retry_after_changed_answers_returns_original_result_without_grading_again(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'legacy-replay'
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    validate = AsyncMock(wraps=service.validate_module)
    monkeypatch.setattr(service, 'validate_module', validate)
    request_id = uuid4().hex
    first = await service.complete_module(learner, 'ai_literacy', request_id=request_id)
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Changed incomplete answer'})
    before = await repo.progress.find_one({'user_id': learner})
    replay = await service.complete_module(learner, 'ai_literacy', request_id=request_id)
    assert replay == first
    validate.assert_awaited_once()
    assert await repo.progress.find_one({'user_id': learner}) == before


@pytest.mark.parametrize('saved_before_error', [False, True])
async def test_lost_receipt_copy_or_response_recovers_the_atomic_original_without_regrading(repo, monkeypatch, saved_before_error):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'lost-legacy-receipt'
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    validate = AsyncMock(wraps=service.validate_module)
    monkeypatch.setattr(service, 'validate_module', validate)
    collection = journal.records()
    monkeypatch.setattr(journal, 'records', lambda: collection)
    insert = collection.insert_one
    failed = False

    async def lose_once(document):
        nonlocal failed
        if not failed:
            failed = True
            if saved_before_error:
                await insert(document)
            raise RuntimeError('Synthetic receipt response lost')
        return await insert(document)

    monkeypatch.setattr(collection, 'insert_one', lose_once)
    request_id = uuid4().hex
    with pytest.raises(RuntimeError, match='response lost'):
        await service.complete_module(learner, 'ai_literacy', request_id=request_id)
    progress = await service.get_progress(learner)
    original = journal.payload(progress, progress.completion_receipt)
    assert progress.total_xp == 125 and progress.modules['ai_literacy']['attempts'] == 1
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Changed after the saved completion'})
    before = await repo.progress.find_one({'user_id': learner})
    assert await service.complete_module(learner, 'ai_literacy', request_id=request_id) == original
    assert await repo.progress.find_one({'user_id': learner}) == before
    assert await collection.count_documents({}) == 1
    validate.assert_awaited_once()


async def test_a_saved_failure_replays_while_a_new_request_can_assess_corrected_answers(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    request_id = uuid4().hex
    first = await service.complete_module('failed-request', 'ai_literacy', request_id=request_id)
    assert first['error'] == 'Validation did not pass'
    await service.store_assessment('failed-request', 'ai_literacy', {'experience': 'Corrected', 'comfort': 'Corrected', 'concern': 'Corrected'})
    assert await service.complete_module('failed-request', 'ai_literacy', request_id=request_id) == first
    passed = await service.complete_module('failed-request', 'ai_literacy', request_id=uuid4().hex)
    assert passed['xp_earned'] == 125
    assert (await service.get_progress('failed-request')).modules['ai_literacy']['attempts'] == 1


async def test_older_receipt_survives_a_later_completion_and_cannot_be_reused_for_another_module(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'two-receipts'
    for module in ('ai_literacy', 'process_mapping'):
        await service.store_assessment(learner, module, {key: 'Original learner choice' for key in service.ASSESSMENT_KEYS[module]})
    first_id = uuid4().hex
    first = await service.complete_module(learner, 'ai_literacy', request_id=first_id)
    await service.complete_module(learner, 'process_mapping', request_id=uuid4().hex)
    before = await repo.progress.find_one({'user_id': learner})
    assert await service.complete_module(learner, 'ai_literacy', request_id=first_id) == first
    with pytest.raises(EnrollmentConflict, match='different module'):
        await service.complete_module(learner, 'process_mapping', request_id=first_id)
    with pytest.raises(EnrollmentConflict, match='Selected competency evidence'):
        await service.complete_module(learner, 'ai_literacy', request_id=first_id, assessment_selection={'review_attempt_id': 'a' * 32})
    assert await repo.progress.find_one({'user_id': learner}) == before
    assert await journal.records().count_documents({}) == 2
    await journal.records().update_one({'request_id': first_id}, {'$set': {'result_sha256': '0' * 64}})
    with pytest.raises(CourseCatalogError, match='integrity'):
        await service.complete_module(learner, 'ai_literacy', request_id=first_id)
    assert await repo.progress.find_one({'user_id': learner}) == before


@pytest.mark.parametrize('request_id', ['', 'not-a-reference', 'A' * 32])
async def test_invalid_completion_identity_does_not_create_progress(repo, monkeypatch, request_id):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    with pytest.raises(EnrollmentConflict, match='valid original request'):
        await service.complete_module('invalid-request', 'ai_literacy', request_id=request_id)
    assert await repo.progress.count_documents({}) == 0


async def test_identical_request_strings_are_scoped_to_each_learner(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    request_id = uuid4().hex
    await service.store_assessment('passing-learner', 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    assert (await service.complete_module('passing-learner', 'ai_literacy', request_id=request_id))['xp_earned'] == 125
    assert (await service.complete_module('other-learner', 'ai_literacy', request_id=request_id))['error'] == 'Validation did not pass'
    assert await journal.records().count_documents({}) == 2
    assert (await service.get_progress('other-learner')).total_xp == 0


async def test_enrollment_continuation_archives_the_pending_legacy_receipt_before_replacing_it(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'continue-legacy'
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    collection = journal.records()
    monkeypatch.setattr(journal, 'records', lambda: collection)
    insert = collection.insert_one
    monkeypatch.setattr(collection, 'insert_one', AsyncMock(side_effect=RuntimeError('Synthetic unavailable receipt copy')))
    request_id = uuid4().hex
    with pytest.raises(RuntimeError, match='unavailable receipt copy'):
        await service.complete_module(learner, 'ai_literacy', request_id=request_id)
    original = await service.get_progress(learner)
    result = journal.payload(original, original.completion_receipt)
    monkeypatch.setattr(collection, 'insert_one', insert)
    enrollment = await repo.ensure_initial(learner)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    continued = await service.complete_module(learner, 'ai_literacy', enrollment_id=enrollment.uuid, request_id=uuid4().hex)
    assert continued['xp_earned'] == 0 and continued['total_xp'] == 125
    record = await collection.find_one({'request_id': request_id})
    assert journal.payload(original, record) == result
    saved = await repo.read_progress(learner, enrollment.uuid)
    assert saved.completion_receipt['attempt_id'] == continued['attempt_id']


async def test_concurrent_identical_legacy_requests_save_one_attempt_and_replay_the_winner(repo, monkeypatch):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'same-request-race'
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    entered, release = asyncio.Event(), asyncio.Event()
    save = service.save_progress
    calls = 0

    async def delay_first(progress):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.wait_for(release.wait(), 30)
        return await save(progress)

    monkeypatch.setattr(service, 'save_progress', delay_first)
    request_id = uuid4().hex
    first = asyncio.create_task(service.complete_module(learner, 'ai_literacy', request_id=request_id))
    try:
        await asyncio.wait_for(entered.wait(), 30)
        winner = await service.complete_module(learner, 'ai_literacy', request_id=request_id)
    finally:
        release.set()
    with pytest.raises(EnrollmentConflict, match='Progress changed'):
        await first
    assert await service.complete_module(learner, 'ai_literacy', request_id=request_id) == winner
    progress = await service.get_progress(learner)
    assert progress.total_xp == 125 and progress.modules['ai_literacy']['attempts'] == 1
    assert await journal.records().count_documents({}) == 1


async def test_live_chat_derives_a_stable_request_reference_and_preserves_explicit_retry_identity(repo, monkeypatch):
    from app.services import chat_tools
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = 'live-chat-retry'
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'Original', 'comfort': 'Original', 'concern': 'Original'})
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner, conversation=SimpleNamespace(uuid='original-conversation'), turn_marker=4), tool_call_id='original-call')
    first = await chat_tools.complete_certification_module(context, 'ai_literacy')
    assert len(first['attempt_id']) == 32
    await service.store_assessment(learner, 'ai_literacy', {'experience': 'New incomplete answer'})
    assert await chat_tools.complete_certification_module(context, 'ai_literacy') == first
    context.tool_call_id = 'new-call'
    assert await chat_tools.complete_certification_module(context, 'ai_literacy', request_id=first['attempt_id']) == first
    different = await chat_tools.complete_certification_module(context, 'ai_literacy')
    assert different['error'] == 'Validation did not pass' and different['attempt_id'] != first['attempt_id']
    assert (await service.get_progress(learner)).total_xp == 125
