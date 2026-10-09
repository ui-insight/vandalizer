"""Exact preserved source bytes, never new execution, judgment or credit."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.transition_records import COLLECTIONS, TransitionRecordReconciliation
from tests.integration import test_certification_outcome_completion as completion
from tests.integration import test_certification_outcome_rubric as grading
from tests.integration import test_certification_enrollments as base

repo = grading.repo
versioned_runtime = base.versioned_runtime
pytestmark = grading.pytestmark


async def inspect(repo, learner):
    async with repo.write_boundary(learner.user_id, learner.uuid, operation='verify_transition_records'):
        return await TransitionRecordReconciliation(repo).inspect(learner.user_id, learner.uuid)


async def test_actual_saved_failures_success_and_completion_are_retained_without_regrading(repo, monkeypatch):
    f, client, _, body, failed, judge = await completion.setup(repo, monkeypatch)
    async with client:
        for scenario, status in ((failed, 400), (body['scenario_attempt_id'], 200)):
            response = await client.post('/certification/modules/validation_qa/complete',
                params={'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex},
                json={**body, 'scenario_attempt_id': scenario})
            assert response.status_code == status, response.text
    service = TransitionRecordReconciliation(repo)
    before = deepcopy(await service.inventory(f.learner.user_id, f.learner.uuid))
    progress = (await repo.read_progress(f.learner.user_id, f.learner.uuid)).model_dump()
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        result = await inspect(repo, f.learner)
        assert await inspect(repo, f.learner) == result
        engine.assert_not_called()
    assert result['record_counts']['completions'] == 2
    assert result['record_counts']['scenarios'] == 2 and result['record_counts']['reviews'] == 1
    assert result['can_activate'] is False and result['credit_transferred'] is False
    assert result['read_only'] and len(result['records_sha256']) == 64
    assert before == await service.inventory(f.learner.user_id, f.learner.uuid)
    assert progress == (await repo.read_progress(f.learner.user_id, f.learner.uuid)).model_dump()
    assert set(result) == {'schema_version', 'source_enrollment_id', 'source_manifest_sha256', 'read_only',
                           'credit_transferred', 'can_activate', 'record_counts', 'records_sha256', 'reconciliation_sha256'}
    judge.assert_awaited_once()


@pytest.mark.parametrize('kind', ['inputs', 'runs', 'decisions', 'reviews', 'scenarios'])
async def test_corrupt_original_bytes_cannot_be_preserved_as_verified_work(repo, monkeypatch, kind):
    f, _, _, _, judge = await grading.fixture(repo, monkeypatch)
    collection = COLLECTIONS[kind].get_motor_collection()
    row = await collection.find_one({'enrollment_id': f.learner.uuid})
    field = 'plan_json' if kind == 'runs' else 'record_json'
    await collection.update_one({'_id': row['_id']}, {'$set': {field: row[field] + ' '}})
    with pytest.raises(CourseCatalogError):
        await inspect(repo, f.learner)
    assert (await collection.find_one({'_id': row['_id']}))[field] == row[field] + ' '
    judge.assert_awaited_once()


@pytest.mark.parametrize('kind,state', [('runs', 'executing'), ('runs', 'uncertain'), ('reviews', 'evaluating')])
async def test_unfinished_operations_block_without_retry_or_cancellation(repo, monkeypatch, kind, state):
    f, _, _, _, judge = await grading.fixture(repo, monkeypatch)
    collection = COLLECTIONS[kind].get_motor_collection()
    row = await collection.find_one({'enrollment_id': f.learner.uuid})
    await collection.update_one({'_id': row['_id']}, {'$set': {'state': state}})
    with pytest.raises(EnrollmentConflict, match='Resolve the original'):
        await inspect(repo, f.learner)
    assert (await collection.find_one({'_id': row['_id']}))['state'] == state
    judge.assert_awaited_once()


async def test_rehashed_contradictory_review_cannot_pass_as_an_original_assessment(repo, monkeypatch):
    import json
    f, _, _, _, judge = await grading.fixture(repo, monkeypatch)
    collection = COLLECTIONS['reviews'].get_motor_collection()
    row = await collection.find_one({'enrollment_id': f.learner.uuid})
    result = json.loads(row['result_json'])
    result['assessment']['passed'] = False
    payload, digest = encode(result)
    await collection.update_one({'_id': row['_id']}, {'$set': {'result_json': payload, 'result_sha256': digest}})
    with pytest.raises(CourseCatalogError, match='reconciliation'):
        await inspect(repo, f.learner)
    judge.assert_awaited_once()


async def test_missing_original_inputs_block_even_when_run_embeds_a_saved_copy(repo, monkeypatch):
    f, _, _, _, _ = await grading.fixture(repo, monkeypatch)
    await COLLECTIONS['inputs'].get_motor_collection().delete_one({'enrollment_id': f.learner.uuid})
    with pytest.raises(CourseCatalogError, match='inputs are missing'):
        await inspect(repo, f.learner)


async def test_changed_bytes_between_reads_are_detected_even_if_claimed_digest_did_not_change(repo, monkeypatch):
    f, _, _, _, _ = await grading.fixture(repo, monkeypatch)
    original = TransitionRecordReconciliation.inventory
    calls = 0
    async def changed(self, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            await COLLECTIONS['scenarios'].get_motor_collection().update_one({'enrollment_id': f.learner.uuid},
                {'$set': {'record_json': 'changed bytes with the original claimed digest'}})
        return await original(self, *args)
    monkeypatch.setattr(TransitionRecordReconciliation, 'inventory', changed)
    with pytest.raises(EnrollmentConflict, match='changed during preservation'):
        await inspect(repo, f.learner)


async def test_requires_an_owned_current_boundary_and_excludes_foreign_history(repo, monkeypatch):
    f, _, _, _, _ = await grading.fixture(repo, monkeypatch)
    service = TransitionRecordReconciliation(repo)
    with pytest.raises(EnrollmentConflict):
        await service.inspect(f.learner.user_id, f.learner.uuid)
    expected = await inspect(repo, f.learner)
    await COLLECTIONS['inputs'].get_motor_collection().insert_one({'uuid': uuid4().hex,
        'user_id': 'another-learner', 'enrollment_id': f.learner.uuid, 'record_json': 'invalid private foreign data'})
    assert await inspect(repo, f.learner) == expected


@pytest.mark.parametrize('boundary', ['progress', 'selection'])
async def test_revoked_guard_cannot_return_a_reconciled_snapshot(repo, monkeypatch, boundary):
    f, _, _, _, _ = await grading.fixture(repo, monkeypatch)
    original = TransitionRecordReconciliation.inventory
    calls = 0
    async def revoked(self, *args):
        nonlocal calls
        calls += 1
        result = await original(self, *args)
        if calls == 2:
            if boundary == 'progress':
                await repo.progress.update_one({'user_id': f.learner.user_id}, {'$set': {'_certification_write_fence': 'revoked'}})
            else:
                await repo.selections.update_one({'user_id': f.learner.user_id}, {'$set': {'active_write.id': 'revoked'}})
        return result
    monkeypatch.setattr(TransitionRecordReconciliation, 'inventory', revoked)
    with pytest.raises(EnrollmentConflict):
        await inspect(repo, f.learner)


@pytest.mark.parametrize('module', ['advanced', 'batch', 'output', 'governance'])
async def test_preserve_other_actual_module_journals_including_private_handoff(repo, monkeypatch, module):
    if module == 'advanced':
        from tests.integration import test_certification_advanced_workflow_reviews as fixture
        f = await fixture.fixture(repo, monkeypatch)
        await fixture.submit(repo, f)
    elif module == 'batch':
        from tests.integration import test_certification_batch_reviews as fixture
        f = await fixture.fixture(repo)
        await fixture.submit(repo, f)
    elif module == 'output':
        from tests.integration import test_certification_output_outcome_reviews as fixture
        f = await fixture.fixture(repo, monkeypatch)
        await fixture.submit(repo, f)
    else:
        from tests.integration import test_certification_governance_handoff as fixture
        f = await fixture.fixture(repo)
        approval = await fixture.release(repo, f)
        failed = await fixture.send(repo, f, fixture.handoff_body(f, approval))
        delivered = await fixture.send(repo, f, fixture.retry_body(failed))
        assert delivered['status'] == 'delivered' and delivered['external_delivery'] is False
    service = TransitionRecordReconciliation(repo)
    before = await service.inventory(f.learner.user_id, f.learner.uuid)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        result = await inspect(repo, f.learner)
        engine.assert_not_called()
    assert result['record_counts']['runs'] >= 1 and result['record_counts']['decisions'] >= 2
    assert await service.inventory(f.learner.user_id, f.learner.uuid) == before


async def test_original_process_map_and_workflow_approval_remain_intact(repo):
    learner, package, _, body = await base.workflow_approval_fixture(repo)
    await base.approve_workflow_design(repo, learner, package, body)
    service = TransitionRecordReconciliation(repo)
    before = await service.inventory(learner.user_id, learner.uuid)
    result = await inspect(repo, learner)
    assert result['record_counts']['processes'] == 1 and result['record_counts']['designs'] == 1
    assert result['record_counts']['inputs'] == 1 and result['record_counts']['runs'] == 0
    assert before == await service.inventory(learner.user_id, learner.uuid)


async def test_connected_original_and_corrected_runs_and_comparison_survive(repo, monkeypatch):
    fixture, original, corrected, providers = await base.connected_pair_fixture(repo, monkeypatch)
    await base.submit_connected_review(repo, fixture, base.connected_review_body(original, corrected))
    service = TransitionRecordReconciliation(repo)
    learner = fixture[0]
    before = await service.inventory(learner.user_id, learner.uuid)
    calls = [provider.call_count for provider in providers]
    result = await inspect(repo, learner)
    assert result['record_counts']['runs'] == 2 and result['record_counts']['decisions'] == 3
    assert before == await service.inventory(learner.user_id, learner.uuid)
    assert calls == [provider.call_count for provider in providers]


async def test_original_completed_recovery_is_verified_without_recovering_again(versioned_runtime):
    import asyncio
    from unittest.mock import AsyncMock
    from app.services import certification_service
    from app.services.certification_versions.recovery_workflow import RecoveryWorkflow
    repo = versioned_runtime
    learner = await repo.ensure_initial('recovery-preservation-learner')
    with patch.object(certification_service, 'validate_module', AsyncMock(side_effect=asyncio.CancelledError())):
        with pytest.raises(asyncio.CancelledError):
            await certification_service.complete_module(learner.user_id, 'ai_literacy', enrollment_id=learner.uuid, request_id=uuid4().hex)
    workflow = RecoveryWorkflow(repo)
    review = await workflow.inspect(learner.user_id, learner.uuid)
    await workflow.submit('synthetic-operator', learner.user_id, learner.uuid, request_id=uuid4().hex,
        review_sha256=review['review_sha256'], reason='Preserve this original interrupted completion receipt')
    service = TransitionRecordReconciliation(repo)
    before = await service.inventory(learner.user_id, learner.uuid)
    with patch.object(RecoveryWorkflow, 'submit') as recover:
        result = await inspect(repo, learner)
        recover.assert_not_called()
    assert result['record_counts']['recoveries'] == 1 and result['record_counts']['completions'] == 1
    assert before == await service.inventory(learner.user_id, learner.uuid)


async def test_prepared_foundations_work_retains_unexecuted_scope_choice(repo):
    learner, _, _, _, _ = await base.learner_decision_fixture(repo, approved=True)
    service = TransitionRecordReconciliation(repo)
    before = await service.inventory(learner.user_id, learner.uuid)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as provider:
        result = await inspect(repo, learner)
        provider.assert_not_called()
    assert result['record_counts']['runs'] == 1 and result['record_counts']['decisions'] == 1
    assert before['runs'][0]['state'] == 'prepared'
    assert before == await service.inventory(learner.user_id, learner.uuid)


async def test_original_extraction_repair_and_source_decisions_remain_readable(repo):
    learner, _, _, _, _, _ = await base.completed_repair_fixture(repo)
    service = TransitionRecordReconciliation(repo)
    before = await service.inventory(learner.user_id, learner.uuid)
    result = await inspect(repo, learner)
    assert result['record_counts']['runs'] >= 1 and result['record_counts']['decisions'] >= 1
    assert before == await service.inventory(learner.user_id, learner.uuid)


async def test_metadata_only_consent_cannot_stage_a_target_with_invalid_original_receipts(repo):
    from tests.integration import test_certification_transition_history as history
    from tests.integration import test_certification_upgrade_decisions as choices
    from app.services.certification_versions.transition_preview import TransitionPreview
    from app.services.certification_versions.upgrade_targets import UpgradeTargetRepository
    source, target, body, decisions = await choices.setup(repo)
    await history.completion(source)
    preview = await TransitionPreview(repo).inspect(source.user_id, source.uuid, target)
    await decisions.accept(source.user_id, {**body, 'preview_sha256': preview['preview_sha256']})
    with pytest.raises(CourseCatalogError):
        await UpgradeTargetRepository(repo).prepare(source.user_id, body['request_id'])
    assert await repo.enrollments.count_documents({'user_id': source.user_id}) == 1
    assert (await repo.current(source.user_id)).uuid == source.uuid
