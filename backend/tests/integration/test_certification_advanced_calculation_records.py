"""Owned calculation persistence in disposable MongoDB only."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from bson import ObjectId
import fitz
import pytest

from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabInput
from app.models.document import SmartDocument
from app.services.certification_versions.advanced_case import load_advanced_case
from app.services.certification_versions.advanced_calculation_records import AdvancedCalculationRepository
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.lab_execution import LabExecutionRepository, execution_plan
from app.services.certification_versions.practical_preparation import PracticalPreparation, PreparationUnavailable
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = enrollment_fixtures.repo


async def fixture(repo, *, enrolled=None):
    if enrolled is None:
        version = enrollment_fixtures.add_scenario_fixture_course(repo)
        folder = repo.catalog.root / version
        draft = CATALOG_ROOT.parent / 'drafts/v5.0'
        (folder / 'advanced-cases').mkdir()
        shutil.copyfile(draft / 'advanced-nodes-case.json', folder / 'advanced-cases/advanced_nodes.json')
        shutil.copyfile(draft / 'documents/budget-justification.pdf', folder / 'documents/budget-justification.pdf')
        exercises = json.loads((folder / 'exercises.json').read_text())
        exercises['advanced_nodes'] = json.loads((draft / 'advanced-nodes-exercise.json').read_text())
        (folder / 'exercises.json').write_text(json.dumps(exercises))
        manifest = json.loads((folder / 'manifest.json').read_text())
        for name in ('advanced-cases/advanced_nodes.json', 'documents/budget-justification.pdf', 'exercises.json'):
            manifest['artifacts'][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        path = repo.catalog.root / 'registry.json'
        registry = json.loads(path.read_text())
        registry['releases'][version]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        path.write_text(json.dumps(registry))
        learner = await repo.ensure_initial('budget-calculation-learner')
        package = repo.catalog.load(version)
    else:
        learner, package = enrolled
    case = load_advanced_case(package)
    pdf_bytes = package.read('documents/' + case.source_filename)
    with fitz.open(stream=pdf_bytes, filetype='pdf') as pdf:
        text = '\n\n'.join(p.get_text() for p in pdf)
    document = await SmartDocument(uuid=uuid4().hex, user_id=learner.user_id, title=case.source_filename,
        path='synthetic/budget.pdf', downloadpath='synthetic/budget.pdf', raw_text=text,
        folder='budget-lab-folder', processing=False, task_status='completed').insert()
    await repo.progress.update_one({'_id': ObjectId(learner.progress_id)}, {'$set': {
        'lab_folder_id': document.folder, 'modules.advanced_nodes.provisioned_docs': [document.uuid]}})
    amounts = {amount.id: amount for amount in case.amounts}
    records = [{'id': check.id, 'operation': 'sum', 'method': 'explicit_learner_arithmetic', 'unit': 'USD',
                'result': check.expected_value, 'interpretation': 'These sums check printed amounts, not period or institutional policy assumptions.',
                'inputs': [{'id': name, 'value': amounts[name].value, 'unit': 'USD', 'source_page': amounts[name].anchor.page,
                            'source_quote': amounts[name].anchor.quote, 'status': 'supported',
                            'explanation': 'I checked the named source row and amount.'} for name in check.inputs]}
               for check in case.calculations]
    body = {'request_id': uuid4().hex, 'case_sha256': case.digest, 'document_id': document.uuid,
            'records': records, 'consent': 'save_source_bound_budget_calculations', 'previous_snapshot_id': None}
    return SimpleNamespace(learner=learner, package=package, case=case, document=document, body=body,
                           storage=SimpleNamespace(read=AsyncMock(return_value=pdf_bytes)))


async def submit(repo, f, inputs=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_budget_calculations') as progress:
        return await (inputs or AdvancedCalculationRepository()).submit(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.body,
            actor_user_id=actor or f.learner.user_id, storage=f.storage)


async def test_preserves_wrong_work_then_linked_correction_after_source_deletion(repo):
    f = await fixture(repo)
    f.body['records'][0]['result'] = '45001.00'
    first = await submit(repo, f)
    assert first['checks']['all_arithmetic_supported'] is False
    await f.document.delete()
    f.storage.read.reset_mock()
    f.storage.read.side_effect = OSError('Original live source removed')
    assert await submit(repo, f) == first
    f.storage.read.assert_not_awaited()
    f.body = {**f.body, 'request_id': uuid4().hex, 'previous_snapshot_id': first['uuid']}
    f.body['records'][0]['result'] = '45000.00'
    revised = await submit(repo, f)
    assert revised['checks']['all_arithmetic_supported'] is True
    assert revised['document'] == first['document']
    assert revised['source_pdf_base64'] == first['source_pdf_base64']
    original = await AdvancedCalculationRepository().get(f.learner.user_id, first['uuid'])
    assert original['request']['records'][0]['result'] == '45001.00'
    assert await AdvancedCalculationRepository().get('other-learner', first['uuid']) is None
    f.storage.read.assert_not_awaited()
    progress = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    assert progress.total_xp == 0 and not progress.certified
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 2


@pytest.mark.parametrize('change', ['actor', 'unassigned', 'foreign_source', 'wrong_bytes', 'ingestion', 'source_race'])
async def test_rejects_unowned_or_changed_source_before_saving(repo, change):
    f = await fixture(repo)
    if change == 'unassigned':
        f.body['document_id'] = uuid4().hex
    elif change == 'foreign_source':
        f.document.user_id = 'other-learner'
        await f.document.save()
    elif change == 'wrong_bytes':
        f.storage.read.return_value = b'wrong assigned file'
    elif change == 'ingestion':
        f.document.processing = True
        await f.document.save()
    elif change == 'source_race':
        original = f.storage.read.return_value

        async def changed_source(_):
            f.document.raw_text += ' changed'
            await f.document.save()
            return original

        f.storage.read.side_effect = changed_source
    with pytest.raises(EnrollmentConflict):
        await submit(repo, f, actor='other-learner' if change == 'actor' else None)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


async def test_request_reuse_cannot_replace_recorded_values(repo):
    f = await fixture(repo)
    first = await submit(repo, f)
    f.body['records'][0]['result'] = '45001.00'
    with pytest.raises(EnrollmentConflict):
        await submit(repo, f)
    assert await AdvancedCalculationRepository().get(f.learner.user_id, first['uuid']) == first


@pytest.mark.parametrize('change', ['missing_parent', 'foreign_parent', 'different_source', 'different_enrollment'])
async def test_revision_cannot_adopt_unrelated_saved_work(repo, change):
    f = await fixture(repo)
    first = await submit(repo, f)
    f.body = {**f.body, 'request_id': uuid4().hex, 'previous_snapshot_id': first['uuid']}
    if change == 'missing_parent':
        f.body['previous_snapshot_id'] = uuid4().hex
    elif change == 'different_source':
        f.body['document_id'] = uuid4().hex
    else:
        raw = await CertificationLabInput.get_motor_collection().find_one({'uuid': first['uuid']})
        key = 'user_id' if change == 'foreign_parent' else 'enrollment_id'
        first[key] = 'another-learner' if key == 'user_id' else uuid4().hex
        serialized, digest = encode(first)
        await CertificationLabInput.get_motor_collection().update_one({'_id': raw['_id']}, {'$set': {
            key: first[key], 'record_json': serialized, 'record_sha256': digest}})
    with pytest.raises(EnrollmentConflict):
        await submit(repo, f)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 1


@pytest.mark.parametrize('change', ['checks', 'request', 'case', 'source_pdf', 'ingestion_text', 'credit', 'execution'])
async def test_rehashed_inner_corruption_cannot_change_calculation_evidence(repo, change):
    f = await fixture(repo)
    saved = await submit(repo, f)
    raw = await CertificationLabInput.get_motor_collection().find_one({'uuid': saved['uuid']})
    value = deepcopy(saved)
    if change == 'checks':
        value['checks']['checks'][0]['computed_value'] = '45001.00'
    elif change == 'request':
        value['request']['records'][0]['result'] = '45001.00'
        value['request_sha256'] = encode(value['request'])[1]
    elif change == 'case':
        value['authored_case']['notice'] += ' Different assignment.'
    elif change == 'source_pdf':
        value['source_pdf_base64'] = 'aW52YWxpZA=='
    elif change == 'ingestion_text':
        value['document']['text'] += ' invented'
    elif change == 'credit':
        value['credit_awarded'] = True
    else:
        value['execution_authorized'] = True
    raw['record_json'], raw['record_sha256'] = encode(value)
    with pytest.raises(CourseCatalogError):
        AdvancedCalculationRepository.decode(raw)


@pytest.mark.parametrize('change', ['oversize', 'revoked_lease', 'no_boundary'])
async def test_storage_limits_and_write_fence_prevent_partial_saves(repo, monkeypatch, change):
    from app.services.certification_versions import advanced_calculation_records
    f = await fixture(repo)
    inputs = AdvancedCalculationRepository()
    if change == 'no_boundary':
        progress = await repo.read_progress(f.learner.user_id, f.learner.uuid)
        with pytest.raises(EnrollmentConflict):
            await inputs.submit(CourseOperation(f.learner.user_id, f.package, progress, True), f.body,
                                actor_user_id=f.learner.user_id, storage=f.storage)
    else:
        if change == 'oversize':
            monkeypatch.setattr(advanced_calculation_records, 'MAX_SNAPSHOT_BYTES', 100)
        else:
            original = inputs._check_lease
            calls = 0

            async def revoke_before_insert(lease):
                nonlocal calls
                calls += 1
                if calls == 2:
                    await repo.progress.update_one({'_id': ObjectId(lease.progress_id)},
                                                   {'$set': {'_certification_write_fence': 'revoked'}})
                await original(lease)

            monkeypatch.setattr(inputs, '_check_lease', revoke_before_insert)
        with pytest.raises(EnrollmentConflict):
            await submit(repo, f, inputs)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


async def test_calculation_record_cannot_be_read_or_dispatched_as_extraction(repo):
    f = await fixture(repo)
    saved = await submit(repo, f)
    with pytest.raises(PreparationUnavailable):
        await PracticalPreparation(repo).get(f.learner.user_id, f.learner.uuid, saved['uuid'])
    with pytest.raises(EnrollmentConflict, match='not executable'):
        execution_plan(saved, {})
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='reject_wrong_executor') as progress:
        with pytest.raises(EnrollmentConflict, match='not executable'):
            await LabExecutionRepository().prepare(CourseOperation(f.learner.user_id, f.package, progress, True),
                                                  saved['uuid'], uuid4().hex, {})
