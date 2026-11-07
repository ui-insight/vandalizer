"""Completion/recovery metadata belongs to the exact preserved source work."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from app.models.certification import CertificationAttempt, CertificationRecoveryRecord
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.upgrade_comparison import UpgradeComparison
from tests.integration import test_certification_upgrade_decisions as choices

repo = choices.repo
pytestmark = choices.pytestmark


async def completion(source, state='rejected'):
    row = {'uuid': uuid4().hex, 'user_id': source.user_id, 'enrollment_id': source.uuid, 'module_id': 'foundations',
           'state': state, 'progress_sha256': 'a' * 64, 'validation_sha256': 'b' * 64, 'result_sha256': 'c' * 64,
           'validation_json': 'private original judgment', 'result_json': 'private original completion result'}
    await CertificationAttempt.get_motor_collection().insert_one(row)
    return row


async def recovery(source, state='completed'):
    row = {'uuid': uuid4().hex, 'user_id': source.user_id, 'enrollment_id': source.uuid, 'state': state,
           'request_sha256': 'a' * 64, 'review_sha256': 'b' * 64, 'result_sha256': 'c' * 64,
           'actor_user_id': 'private-recovery-operator', 'review_json': 'private recovery review', 'result_json': 'private recovery result'}
    await CertificationRecoveryRecord.get_motor_collection().insert_one(row)
    return row


async def test_all_original_results_are_visible_in_the_plan_without_leaking_content_or_changing_credit(repo):
    source, target, _, _ = await choices.setup(repo)
    saved = [await completion(source, state) for state in ('applied', 'rejected', 'failed')]
    completed = await recovery(source)
    collections = (repo.progress, repo.selections, CertificationAttempt.get_motor_collection(), CertificationRecoveryRecord.get_motor_collection())
    before = deepcopy([await collection.find({}).to_list(None) for collection in collections])
    result = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    plan = result['preservation_plan']
    assert {entry['record_id'] for entry in plan['entries']} == {item['uuid'] for item in [*saved, completed]}
    assert all(entry['proposed_action'] == 'retain_original_result' for entry in plan['entries'])
    assert plan['reconciliation_required_count'] == 0
    assert 'private' not in json.dumps(result)
    assert result['target']['transferred_outcome_count'] == 0
    assert before == [await collection.find({}).to_list(None) for collection in collections]


async def test_unfinished_recovery_blocks_new_consent_even_without_an_active_write(repo):
    source, target, body, decisions = await choices.setup(repo)
    saved = await recovery(source, 'started')
    preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    assert preview['work_in_flight'] is False
    assert preview['preservation_plan']['reconciliation_required_count'] == 1
    assert preview['preservation_plan']['entries'][0]['record_id'] == saved['uuid']
    with pytest.raises(EnrollmentConflict, match='Resolve unfinished'):
        await decisions.accept(source.user_id, {**body, 'preview_sha256': preview['preview_sha256']})
    assert await decisions.records.count_documents({}) == 0


@pytest.mark.parametrize('kind', ['completion', 'recovery'])
async def test_new_terminal_history_after_consent_requires_a_new_reviewed_choice(repo, kind):
    source, _, body, decisions = await choices.setup(repo)
    original = await decisions.accept(source.user_id, body)
    await (completion(source) if kind == 'completion' else recovery(source))
    with pytest.raises(EnrollmentConflict, match='changed after the choice'):
        async with decisions.hold_reviewed_choice(source.user_id, body['request_id']):
            pytest.fail('New terminal history was hidden from the reviewed snapshot')
    assert await decisions.get(source.user_id, body['request_id']) == original


@pytest.mark.parametrize('kind', ['completion', 'recovery'])
async def test_changed_terminal_receipt_during_preview_is_detected_without_a_progress_write(repo, monkeypatch, kind):
    source, target, _, _ = await choices.setup(repo)
    record = await (completion(source) if kind == 'completion' else recovery(source))
    collection = (CertificationAttempt if kind == 'completion' else CertificationRecoveryRecord).get_motor_collection()
    original = CredentialRepository.for_enrollment
    changed = False
    async def mutate(self, *args):
        nonlocal changed
        if not changed:
            changed = True
            await collection.update_one({'uuid': record['uuid']}, {'$set': {'result_sha256': 'e' * 64}})
        return await original(self, *args)
    monkeypatch.setattr(CredentialRepository, 'for_enrollment', mutate)
    with pytest.raises(EnrollmentConflict, match='changed during the preview'):
        await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)


@pytest.mark.parametrize('kind', ['completion', 'recovery'])
async def test_foreign_history_cannot_enter_the_preservation_plan(repo, kind):
    source, target, _, _ = await choices.setup(repo)
    record = await (completion(source) if kind == 'completion' else recovery(source))
    collection = (CertificationAttempt if kind == 'completion' else CertificationRecoveryRecord).get_motor_collection()
    await collection.update_one({'uuid': record['uuid']}, {'$set': {'user_id': 'another-user'}})
    assert (await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target))['preservation_plan']['entries'] == []
