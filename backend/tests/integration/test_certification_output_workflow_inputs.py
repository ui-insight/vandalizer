"""Assigned source and owned output configuration capture in disposable MongoDB."""
import base64
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
from pydantic import ValidationError

from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.models.document import SmartDocument
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.lab_execution import execution_plan
from app.services.certification_versions.output_case import load_output_case
from app.services.certification_versions.output_workflow_inputs import OutputWorkflowInputRepository
from app.services.certification_versions.runtime import CourseOperation

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = enrollment_fixtures.repo


async def fixture(repo, *, enrolled=None):
    if enrolled is None:
        version = enrollment_fixtures.add_scenario_fixture_course(repo)
        folder = repo.catalog.root / version
        draft = CATALOG_ROOT.parent / 'drafts/v5.0'
        (folder / 'output-cases').mkdir()
        shutil.copyfile(draft / 'output-delivery-case.json', folder / 'output-cases/output_delivery.json')
        shutil.copyfile(draft / 'documents/progress-report-year2.pdf', folder / 'documents/progress-report-year2.pdf')
        exercises = json.loads((folder / 'exercises.json').read_text())
        exercises['output_delivery'] = json.loads((draft / 'output-delivery-exercise.json').read_text())
        (folder / 'exercises.json').write_text(json.dumps(exercises))
        manifest = json.loads((folder / 'manifest.json').read_text())
        for name in ('output-cases/output_delivery.json', 'documents/progress-report-year2.pdf', 'exercises.json'):
            manifest['artifacts'][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        registry_path = repo.catalog.root / 'registry.json'
        registry = json.loads(registry_path.read_text())
        registry['releases'][version]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        registry_path.write_text(json.dumps(registry))
        learner = await repo.ensure_initial('output-workflow-learner')
        package = repo.catalog.load(version)
    else:
        learner, package = enrolled
    case = load_output_case(package)
    source = package.read('documents/' + case.source_filename)
    with fitz.open(stream=source, filetype='pdf') as pdf:
        text = '\n\n'.join(page.get_text() for page in pdf)
    document = await SmartDocument(uuid=uuid4().hex, user_id=learner.user_id, title=case.source_filename,
        path='synthetic/progress.pdf', downloadpath='synthetic/progress.pdf', raw_text=text,
        folder='output-lab-folder', processing=False, task_status='completed').insert()
    await repo.progress.update_one({'_id': ObjectId(learner.progress_id)}, {'$set': {
        'lab_folder_id': document.folder, 'modules.output_delivery.provisioned_docs': [document.uuid]}})
    task = await WorkflowStepTask(name='Prompt', data={'prompt': 'Prepare a source-grounded report.'}).insert()
    step = await WorkflowStep(name='Report review', tasks=[task.id]).insert()
    workflow = await Workflow(name='Owned progress report', user_id=learner.user_id, steps=[step.id], share_token='private-share-token').insert()
    body = {'request_id': uuid4().hex, 'workflow_id': str(workflow.id), 'case_sha256': case.digest, 'consent': 'capture_output_workflow_inputs'}
    return SimpleNamespace(learner=learner, package=package, case=case, document=document, workflow=workflow,
        task=task, step=step, body=body, source=source, storage=SimpleNamespace(read=AsyncMock(return_value=source)))


async def capture(repo, f, inputs=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='capture_output_workflow') as progress:
        return await (inputs or OutputWorkflowInputRepository()).capture(
            CourseOperation(f.learner.user_id, f.package, progress, True), f.body,
            actor_user_id=actor or f.learner.user_id, storage=f.storage)


async def test_preserves_original_configuration_pdf_and_ingestion_after_deletion(repo):
    f = await fixture(repo)
    saved = await capture(repo, f)
    assert base64.b64decode(saved['documents'][0]['source_pdf_base64']) == f.source
    assert saved['documents'][0]['text'] == f.document.raw_text
    assert saved['case'] == f.case.public_definition()
    assert 'source_checks' not in saved['case'] and 'review_guidance' not in saved['case']
    assert 'share_token' not in saved['artifact']['workflow']
    assert saved['execution_authorized'] is saved['credit_awarded'] is False
    await f.document.delete()
    await f.workflow.delete()
    await f.task.delete()
    f.storage.read.reset_mock()
    assert await capture(repo, f) == saved
    f.storage.read.assert_not_awaited()
    assert await OutputWorkflowInputRepository().get(f.learner.user_id, saved['uuid']) == saved
    assert await OutputWorkflowInputRepository().get('foreign', saved['uuid']) is None
    with pytest.raises(EnrollmentConflict, match='not executable'):
        execution_plan(saved, {})
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'foreign_workflow', 'foreign_source', 'wrong_folder', 'wrong_bytes',
    'ingestion', 'case', 'consent', 'client_evidence', 'unassigned_source', 'source_race', 'workflow_race'])
async def test_rejects_unowned_or_changed_inputs_before_saving(repo, monkeypatch, change):
    f = await fixture(repo)
    inputs = OutputWorkflowInputRepository()
    if change == 'foreign_workflow':
        f.workflow.user_id = 'foreign'
        await f.workflow.save()
    elif change == 'foreign_source':
        f.document.user_id = 'foreign'
        await f.document.save()
    elif change == 'wrong_folder':
        f.document.folder = 'other-lab'
        await f.document.save()
    elif change == 'wrong_bytes':
        f.storage.read.return_value = b'unrelated source'
    elif change == 'ingestion':
        f.document.processing = True
        await f.document.save()
    elif change == 'case':
        f.body['case_sha256'] = 'a' * 64
    elif change == 'consent':
        f.body['consent'] = 'execute_workflow'
    elif change == 'client_evidence':
        f.body['artifact'] = {'made_up': True}
    elif change == 'unassigned_source':
        await repo.progress.update_one({'_id': ObjectId(f.learner.progress_id)}, {'$set': {'modules.output_delivery.provisioned_docs': []}})
    elif change == 'source_race':
        async def mutate_source(*_args):
            f.document.raw_text += '\nChanged after selection'
            await f.document.save()
            return f.source
        f.storage.read.side_effect = mutate_source
    elif change == 'workflow_race':
        original = inputs._read_artifact
        calls = 0
        async def mutate_workflow(*args):
            nonlocal calls
            value = await original(*args)
            calls += 1
            if calls == 1:
                f.task.data['prompt'] = 'Changed after selection'
                await f.task.save()
            return value
        monkeypatch.setattr(inputs, '_read_artifact', mutate_workflow)
    with pytest.raises((EnrollmentConflict, ValidationError)):
        await capture(repo, f, inputs, actor='foreign' if change == 'actor' else None)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('change', ['pdf', 'ingestion', 'workflow', 'public_case', 'private_case', 'authority'])
async def test_rehashed_nested_changes_do_not_become_original_evidence(repo, change):
    f = await fixture(repo)
    saved = deepcopy(await capture(repo, f))
    if change == 'pdf':
        saved['documents'][0]['source_pdf_base64'] = base64.b64encode(b'changed bytes').decode()
    elif change == 'ingestion':
        saved['documents'][0]['text'] = 'Changed ingestion text'
    elif change == 'workflow':
        saved['artifact']['workflow']['name'] = 'Changed original workflow'
    elif change == 'public_case':
        saved['case']['task'] = 'Changed public task'
    elif change == 'private_case':
        saved['authored_case']['source_checks'][0]['interpretation'] = 'Changed private criterion with enough text to pass field validation.'
    elif change == 'authority':
        saved['execution_authorized'] = True
    serialized, digest = encode(saved)
    raw = await CertificationLabInput.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw.update(record_json=serialized, record_sha256=digest)
    with pytest.raises(CourseCatalogError):
        OutputWorkflowInputRepository.decode(raw)


async def test_original_request_cannot_be_repurposed_to_another_owned_workflow(repo):
    f = await fixture(repo)
    await capture(repo, f)
    other = await Workflow(name='Another output workflow', user_id=f.learner.user_id).insert()
    f.body['workflow_id'] = str(other.id)
    with pytest.raises(EnrollmentConflict):
        await capture(repo, f)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 1
