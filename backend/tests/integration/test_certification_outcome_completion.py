"""Authenticated selected-outcome completion using isolated synthetic packages."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import CertificationAttempt, CertificationReviewAttempt, CertificationScenarioAttempt
from app.routers.certification import router
from app.services.certification_versions import runtime
from app.services.certification_versions.attempts import AttemptRepository, encode
from app.services.certification_versions.outcome_credit import verified_credit_snapshot
from app.services.certification_versions.credentials import CredentialRepository
from tests.integration import test_certification_outcome_rubric as grading

repo = grading.repo
pytestmark = grading.pytestmark


async def setup(repo, monkeypatch, *, wrong_execution=False, single_module=False):
    f, review, failed, passed, judge = await grading.fixture(repo, monkeypatch, wrong_execution=wrong_execution, single_module=single_module)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    monkeypatch.setattr('app.services.certification_service._fire_certification_complete_hooks', AsyncMock())
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=f.learner.user_id)
    client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
    body = {'consent': 'complete_selected_saved_outcomes', 'review_attempt_id': review, 'scenario_attempt_id': passed}
    return f, client, app, body, failed, judge


async def test_explicit_completion_records_original_outcomes_once_and_replays_the_same_request(repo, monkeypatch):
    f, client, _, body, failed, judge = await setup(repo, monkeypatch)
    params = {'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}
    path = '/certification/modules/validation_qa/complete'
    async with client:
        definition = await client.get('/certification/course', params={'enrollment_id': f.learner.uuid})
        assert definition.status_code == 200 and definition.json()['selected_outcome_completion'] is True
        response = await client.post(path, params=params, json=body)
        assert response.status_code == 200, response.text
        expected_xp = next(item.base_xp for item in f.package.manifest.modules if item.id == 'validation_qa')
        assert response.json()['xp_earned'] == expected_xp
        saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        credit = saved.modules['validation_qa']
        assert credit['completed'] and credit['stars'] == 1 and credit['xp_earned'] == expected_xp
        snapshot = verified_credit_snapshot(f.package, saved, 'validation_qa', credit['outcome_credit'], expected_attempt_id=params['request_id'])
        assert snapshot['all_required_outcomes_supported'] and len(snapshot['outcomes']) == 3
        before = await repo.progress.find_one({'user_id': f.learner.user_id})
        for retry_body in (body, None):
            repeated = await client.post(path, params=params, json=retry_body)
            assert repeated.status_code == 200 and repeated.json() == response.json()
        changed = await client.post(path, params=params, json={**body, 'scenario_attempt_id': failed})
        assert changed.status_code == 409
        after = await repo.progress.find_one({'user_id': f.learner.user_id})
        # The write fence rotates, while earned content remains byte-equivalent.
        for value in (before, after):
            value.pop('_certification_write_fence', None)
        assert after == before
        assert await CertificationAttempt.get_motor_collection().count_documents({}) == 1
        request = await CertificationAttempt.get_motor_collection().find_one({'uuid': params['request_id']})
        assert request['state'] == 'applied'
        assert AttemptRepository.assessment_selection(request) == {key: body[key] for key in ('review_attempt_id', 'scenario_attempt_id')}
    judge.assert_awaited_once()


@pytest.mark.parametrize('lost_receipt_reply', [False, True])
async def test_new_request_for_same_saved_outcomes_preserves_original_earned_credit(repo, monkeypatch, lost_receipt_reply):
    f, client, _, body, _, judge = await setup(repo, monkeypatch)
    first_id, repeat_id = uuid4().hex, uuid4().hex
    path = '/certification/modules/validation_qa/complete'
    async with client:
        first = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': first_id}, json=body)
        assert first.status_code == 200, first.text
        original = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        if lost_receipt_reply:
            finish = AttemptRepository.finish
            interrupted = False
            async def lose_once(journal, record, result, **kwargs):
                nonlocal interrupted
                if record['uuid'] == repeat_id and not interrupted:
                    interrupted = True
                    raise RuntimeError('Synthetic lost repeat receipt response')
                return await finish(journal, record, result, **kwargs)
            monkeypatch.setattr(AttemptRepository, 'finish', lose_once)
            with pytest.raises(RuntimeError, match='Synthetic lost repeat receipt'):
                await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': repeat_id}, json=body)
        repeated = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': repeat_id}, json=body)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()['xp_earned'] == 0 and repeated.json()['attempt_id'] == repeat_id
        saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        assert saved.modules['validation_qa'] == original.modules['validation_qa']
        assert saved.total_xp == original.total_xp
        snapshot = verified_credit_snapshot(f.package, saved, 'validation_qa', saved.modules['validation_qa']['outcome_credit'], expected_attempt_id=first_id)
        assert snapshot['all_required_outcomes_supported']
        replay = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': repeat_id}, json=body)
        assert replay.json() == repeated.json()
        first_replay = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': first_id}, json=body)
        assert first_replay.json() == first.json()
    # Request receipts remain separately auditable; the module records one
    # earned assessment using the same immutable review/scenario evidence.
    assert await CertificationAttempt.get_motor_collection().count_documents({}) == 2
    judge.assert_awaited_once()


async def test_new_saved_scenario_is_a_distinct_completion_and_its_repeat_keeps_that_credit(repo, monkeypatch):
    f, client, _, body, _, judge = await setup(repo, monkeypatch)
    path = '/certification/modules/validation_qa/complete'
    bank = grading.module_bank(f.package, 'validation_qa')
    second_scenario = uuid4().hex
    async with client:
        first = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=body)
        assert first.status_code == 200, first.text
        await grading.base.submit_scenario(repo, f.learner, f.package, bank,
            {q.id: q.correct_choice_id for q in bank.questions}, second_scenario)
        changed = {**body, 'scenario_attempt_id': second_scenario}
        second = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=changed)
        assert second.status_code == 200, second.text
        saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        assert saved.modules['validation_qa']['attempts'] == 2
        assert saved.modules['validation_qa']['completion_attempt_id'] == second.json()['attempt_id']
        repeat = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=changed)
        assert repeat.status_code == 200, repeat.text
        assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).modules == saved.modules
        assert second.json()['xp_earned'] == repeat.json()['xp_earned'] == 0
    judge.assert_awaited_once()


async def test_repeat_cannot_replace_a_corrupt_original_credit_record(repo, monkeypatch):
    f, client, _, body, _, _ = await setup(repo, monkeypatch)
    path = '/certification/modules/validation_qa/complete'
    async with client:
        first = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=body)
        assert first.status_code == 200, first.text
        await repo.progress.update_one({'enrollment_id': f.learner.uuid}, {'$set': {
            'modules.validation_qa.outcome_credit.validation_sha256': '0' * 64,
        }})
        before = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        repeat = await client.post(path, params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=body)
        assert repeat.status_code == 503, repeat.text
        after = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        assert after.modules == before.modules and after.total_xp == before.total_xp


@pytest.mark.parametrize('lost_issuance', [False, True])
async def test_graduation_freezes_original_outcomes_and_recovers_issuance_without_regrading(repo, monkeypatch, lost_issuance):
    f, client, _, body, _, judge = await setup(repo, monkeypatch, single_module=True)
    params = {'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}
    path = '/certification/modules/validation_qa/complete'
    original_persist = CredentialRepository.persist
    async def unavailable(*args, **kwargs):
        raise RuntimeError('Synthetic interrupted credential persistence')
    async with client:
        if lost_issuance:
            monkeypatch.setattr(CredentialRepository, 'persist', unavailable)
            with pytest.raises(RuntimeError, match='interrupted credential'):
                await client.post(path, params=params, json=body)
            saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
            pending = saved.pending_credential
            assert saved.certified and len(pending['outcomes']) == 3
            monkeypatch.setattr(CredentialRepository, 'persist', original_persist)
        completed = await client.post(path, params=params, json=body)
        assert completed.status_code == 200, completed.text
        assert completed.json()['certified'] is True and completed.json()['level'] == 'validated'
        credentials = CredentialRepository()
        record = await credentials.for_enrollment(f.learner.user_id, f.learner.uuid)
        assert len(record.outcomes) == 3 and len(record.evidence) == 1
        assert record.evidence[0]['basis'] == 'selected_required_outcomes'
        assert {item['attempt_id'] for item in record.evidence[0]['assessment_snapshot']['selected_receipts']} == {body['review_attempt_id'], body['scenario_attempt_id']}
        if lost_issuance:
            assert record.model_dump(mode='json') == pending
        original = record.model_dump_json()
        again = await client.post(path, params=params, json=body)
        assert again.json() == completed.json()
        later = await client.post(path, params={**params, 'request_id': uuid4().hex}, json=body)
        assert later.status_code == 200 and later.json()['xp_earned'] == 0
        assert (await credentials.for_enrollment(f.learner.user_id, f.learner.uuid)).model_dump_json() == original
        assert await credentials.records.count_documents({}) == 1
        saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        assert saved.pending_credential is None
    judge.assert_awaited_once()


@pytest.mark.parametrize('invalid', ['missing_scenario', 'failed_scenario', 'wrong_execution'])
async def test_partial_or_failed_evidence_cannot_earn_module_credit(repo, monkeypatch, invalid):
    f, client, _, body, failed, judge = await setup(repo, monkeypatch, wrong_execution=invalid == 'wrong_execution')
    if invalid == 'missing_scenario':
        body.pop('scenario_attempt_id')
    if invalid == 'failed_scenario':
        body['scenario_attempt_id'] = failed
    async with client:
        response = await client.post('/certification/modules/validation_qa/complete',
            params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}, json=body)
        assert response.status_code == 400, response.text
    saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    assert saved.total_xp == 0 and not saved.certified
    assert not saved.modules['validation_qa'].get('completed')
    assert 'outcome_credit' not in saved.modules['validation_qa']
    judge.assert_awaited_once()


@pytest.mark.parametrize('selection', ['missing', 'failed'])
async def test_participation_and_high_xp_cannot_replace_required_selected_evidence(repo, monkeypatch, selection):
    f, client, _, body, failed, judge = await setup(repo, monkeypatch, single_module=True)
    # Synthetic preexisting participation/imported XP must not become competency
    # credit, even when an unselected passing assessment also exists in history.
    position = {'module_id': 'validation_qa',
                'lesson_id': f.package.manifest.modules[0].lesson_ids[-1]}
    answers = {'reflection': 'I read every lesson and understand the course.'}
    await repo.progress.update_one({'user_id': f.learner.user_id}, {'$set': {
        'total_xp': 9999, 'level': 'architect', 'learning_position': position,
        'modules.validation_qa.self_assessment': answers,
    }})
    if selection == 'missing':
        body.pop('scenario_attempt_id')
    else:
        body['scenario_attempt_id'] = failed
    async with client:
        params = {'enrollment_id': f.learner.uuid}
        before = await client.get('/certification/progress', params=params)
        assert before.status_code == 200 and before.json()['certified'] is False
        response = await client.post('/certification/modules/validation_qa/complete',
            params={**params, 'request_id': uuid4().hex}, json=body)
        assert response.status_code == 400, response.text
        download = await client.get('/certification/certificate', params=params)
        assert download.status_code == 404, download.text
    saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    assert saved.total_xp == 9999 and saved.level == 'architect' and not saved.certified
    assert saved.learning_position == position
    assert saved.modules['validation_qa']['self_assessment'] == answers
    assert not saved.modules['validation_qa'].get('completed')
    assert 'outcome_credit' not in saved.modules['validation_qa']
    assert await CredentialRepository().records.count_documents({}) == 0
    judge.assert_awaited_once()


async def test_completion_requires_explicit_consent_request_identity_and_authenticated_course(repo, monkeypatch):
    f, client, app, body, _, judge = await setup(repo, monkeypatch)
    path = '/certification/modules/validation_qa/complete'
    params = {'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}
    async with client:
        for bad in ({**body, 'consent': 'grade_for_me'}, {**body, 'passed': True}, {'consent': body['consent']},
                    {**body, 'review_attempt_id': 'latest'}):
            assert (await client.post(path, params=params, json=bad)).status_code == 422
        assert (await client.post(path, params={'enrollment_id': f.learner.uuid}, json=body)).status_code == 422
        assert (await client.post(path, params={**params, 'enrollment_id': 'different'}, json=body)).status_code == 409
        assert await CertificationAttempt.get_motor_collection().count_documents({}) == 0
        app.dependency_overrides.clear()
        assert (await client.post(path, params=params, json=body)).status_code == 401
    judge.assert_awaited_once()


@pytest.mark.parametrize('change,status', [('review_deleted', 409), ('review_result', 503), ('scenario_record', 503)])
async def test_completion_rechecks_original_receipts_after_a_passing_readiness_preview(repo, monkeypatch, change, status):
    f, client, _, body, _, judge = await setup(repo, monkeypatch, single_module=True)
    path = '/certification/modules/validation_qa'
    selected = {key: body[key] for key in ('review_attempt_id', 'scenario_attempt_id')}
    params = {'enrollment_id': f.learner.uuid}
    async with client:
        preview = await client.get(path + '/readiness', params={**params, **selected})
        assert preview.status_code == 200 and preview.json()['all_required_outcomes_supported'] is True
        if change == 'review_deleted':
            await CertificationReviewAttempt.get_motor_collection().delete_one({'uuid': body['review_attempt_id']})
        elif change == 'review_result':
            records = CertificationReviewAttempt.get_motor_collection()
            raw = await records.find_one({'uuid': body['review_attempt_id']})
            result = json.loads(raw['result_json'])
            result['assessment']['outcomes'].pop()
            serialized, digest = encode(result)
            await records.update_one({'_id': raw['_id']}, {'$set': {'result_json': serialized, 'result_sha256': digest}})
        else:
            await CertificationScenarioAttempt.get_motor_collection().update_one(
                {'uuid': body['scenario_attempt_id']}, {'$set': {'record_sha256': '0' * 64}})
        response = await client.post(path + '/complete', params={**params, 'request_id': uuid4().hex}, json=body)
        assert response.status_code == status, response.text
        assert (await client.get('/certification/certificate', params=params)).status_code == 404
    saved = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    assert saved.total_xp == 0 and not saved.certified
    assert not saved.modules['validation_qa'].get('completed')
    assert 'outcome_credit' not in saved.modules['validation_qa']
    assert await CredentialRepository().records.count_documents({}) == 0
    judge.assert_awaited_once()
