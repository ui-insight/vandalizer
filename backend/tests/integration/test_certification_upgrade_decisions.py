"""Durable internal consent records using isolated synthetic release flags."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.rubrics import competency_v5
from app.services.certification_versions.upgrade_comparison import UpgradeComparison, UpgradeUnavailable
from app.services.certification_versions.upgrade_decisions import UpgradeDecisionRepository
from tests.integration import test_certification_enrollments as fixtures

repo = fixtures.repo
pytestmark = fixtures.pytestmark


async def setup(repo, *, verified=True):
    source = await repo.ensure_initial('upgrade-choice-learner')
    target = fixtures.add_scenario_fixture_course(repo)
    if verified:
        folder = repo.catalog.root / target
        content = Path(competency_v5.__file__).read_bytes()
        (folder / 'rubric.py').write_bytes(content)
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest.update(maximum_stars=1, star_bonus_xp=0)
        manifest['artifacts']['rubric.py'] = hashlib.sha256(content).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        registry_path = repo.catalog.root / 'registry.json'
        registry = json.loads(registry_path.read_text())
        registry['releases'][target]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        registry_path.write_text(json.dumps(registry))
    fixtures.set_upgrade_offer(repo, source.course_version, target)
    preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    body = {'request_id': uuid4().hex, 'source_enrollment_id': source.uuid, 'target_version': target,
            'preview_sha256': preview['preview_sha256'], 'consent': 'preserve_original_work_and_require_all_new_outcomes'}
    return source, target, body, UpgradeDecisionRepository(repo)


async def test_choice_preserves_exact_preview_without_selecting_enrolling_or_awarding(repo):
    source, _, body, decisions = await setup(repo)
    collections = (repo.enrollments, repo.selections, repo.progress)
    before = deepcopy([await collection.find({}).to_list(None) for collection in collections])
    results = await asyncio.gather(*(decisions.accept(source.user_id, body) for _ in range(6)))
    assert all(result == results[0] for result in results)
    record = results[0]
    assert record.activated is record.credit_transferred is False
    assert record.requires_fresh_activation_check is True
    assert record.preview['source']['enrollment_id'] == source.uuid
    assert record.preview['target']['required_outcome_count'] == 33
    assert record.preview['target']['transferred_outcome_count'] == 0
    assert await decisions.records.count_documents({}) == 1
    assert before == [await collection.find({}).to_list(None) for collection in collections]
    original = record.model_dump_json()
    record.preview['target']['transferred_outcome_count'] = 33
    assert (await decisions.get(source.user_id, body['request_id'])).model_dump_json() == original
    assert await decisions.get('another-user', body['request_id']) is None


async def test_retry_after_lost_insertion_response_keeps_original_consent_even_after_new_work(repo, monkeypatch):
    source, _, body, decisions = await setup(repo)
    original = decisions.records.insert_one
    async def lost_reply(value):
        await original(value)
        raise RuntimeError('Synthetic lost persistence response')
    monkeypatch.setattr(decisions.records, 'insert_one', lost_reply)
    with pytest.raises(RuntimeError, match='lost persistence'):
        await decisions.accept(source.user_id, body)
    preserved = await decisions.get(source.user_id, body['request_id'])
    monkeypatch.setattr(decisions.records, 'insert_one', original)
    await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'total_xp': 125}})
    replay = await decisions.accept(source.user_id, body)
    assert replay == preserved
    assert replay.preview['source']['total_xp'] == 0
    assert replay.requires_fresh_activation_check is True
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 125


@pytest.mark.parametrize('change', ['progress', 'saved_work', 'withdrawn_offer', 'unverified_target'])
async def test_changed_or_unavailable_plan_never_records_fresh_consent(repo, change):
    source, target, body, decisions = await setup(repo, verified=change != 'unverified_target')
    if change == 'progress':
        await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'total_xp': 125}})
    elif change == 'saved_work':
        await fixtures.insert_execution_summary(source.user_id, source.uuid, 'prepared')
    elif change == 'withdrawn_offer':
        fixtures.set_upgrade_offer(repo, source.course_version, target, enabled=False)
    with pytest.raises((EnrollmentConflict, UpgradeUnavailable)):
        await decisions.accept(source.user_id, body)
    assert await decisions.records.count_documents({}) == 0


@pytest.mark.parametrize('state', ['executing', 'uncertain'])
async def test_exact_preview_still_cannot_accept_unresolved_operation(repo, state):
    source, target, body, decisions = await setup(repo)
    await fixtures.insert_execution_summary(source.user_id, source.uuid, state)
    preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    body['preview_sha256'] = preview['preview_sha256']
    with pytest.raises(EnrollmentConflict, match='Resolve unfinished'):
        await decisions.accept(source.user_id, body)
    assert await decisions.records.count_documents({}) == 0


async def test_request_cannot_be_rebound_to_other_actor_preview_or_consent(repo):
    source, _, body, decisions = await setup(repo)
    await decisions.accept(source.user_id, body)
    with pytest.raises(EnrollmentConflict, match='unavailable'):
        await decisions.accept('other-user', body)
    with pytest.raises(EnrollmentConflict, match='different preservation'):
        await decisions.accept(source.user_id, {**body, 'preview_sha256': 'f' * 64})
    for bad in ({**body, 'consent': 'activate_now'}, {**body, 'transferred_credit': 33}, {**body, 'request_id': 'latest'}):
        with pytest.raises(ValidationError):
            await decisions.accept(source.user_id, bad)
    assert await decisions.records.count_documents({}) == 1


async def test_corrupt_preserved_choice_never_replays_as_valid(repo):
    source, _, body, decisions = await setup(repo)
    await decisions.accept(source.user_id, body)
    await decisions.records.update_one({'uuid': body['request_id']}, {'$set': {'record_json': '{}'}})
    with pytest.raises(CourseCatalogError, match='integrity'):
        await decisions.accept(source.user_id, body)


async def test_active_course_write_blocks_acceptance_of_even_a_matching_preview(repo):
    source, target, body, decisions = await setup(repo)
    async with repo.write_boundary(source.user_id, source.uuid):
        preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
        body['preview_sha256'] = preview['preview_sha256']
        with pytest.raises(EnrollmentConflict, match='Resolve unfinished'):
            await decisions.accept(source.user_id, body)
    assert await decisions.records.count_documents({}) == 0


async def test_missing_confirmation_can_retry_original_identity_without_a_second_record(repo, monkeypatch):
    source, _, body, decisions = await setup(repo)
    monkeypatch.setattr(decisions.records, 'insert_one', AsyncMock())
    with pytest.raises(EnrollmentConflict, match='could not be confirmed'):
        await decisions.accept(source.user_id, body)
    assert await decisions.records.count_documents({}) == 0


async def test_new_reviewed_choice_preserves_earlier_consent_and_all_saved_work(repo):
    source, target, body, decisions = await setup(repo)
    first = await decisions.accept(source.user_id, body)
    saved = await fixtures.insert_execution_summary(source.user_id, source.uuid, 'prepared')
    with pytest.raises(EnrollmentConflict, match='changed'):
        await decisions.accept(source.user_id, {**body, 'request_id': uuid4().hex})
    preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    second_body = {**body, 'request_id': uuid4().hex, 'preview_sha256': preview['preview_sha256']}
    second = await decisions.accept(source.user_id, second_body)
    assert second.preview['preservation_plan']['entries'][0]['record_id'] == saved['uuid']
    assert (await decisions.get(source.user_id, body['request_id'])) == first
    assert await decisions.records.count_documents({}) == 2
    assert (await repo.current(source.user_id)).uuid == source.uuid


async def test_credential_needs_preservation_before_accepting_a_new_plan(repo):
    source, target, body, decisions = await setup(repo)
    await repo.progress.update_one({'_id': ObjectId(source.progress_id)}, {'$set': {'certified': True}})
    preview = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    assert preview['credential_needs_preservation'] is True
    with pytest.raises(EnrollmentConflict, match='preserve the original credential'):
        await decisions.accept(source.user_id, {**body, 'preview_sha256': preview['preview_sha256']})
    assert await decisions.records.count_documents({}) == 0


async def test_fresh_foreign_source_reference_cannot_record_a_decision(repo):
    _, _, body, decisions = await setup(repo)
    with pytest.raises(EnrollmentConflict, match='selected course changed'):
        await decisions.accept('foreign-user', body)
    assert await decisions.records.count_documents({}) == 0
