"""Owned revisions and exact representative sources in disposable MongoDB."""
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

from tests.integration import test_certification_enrollments as enrollment_fixtures
from app.models.certification import CertificationLabInput, CertificationLabExecution
from app.models.document import SmartDocument
from app.models.search_set import SearchSet, SearchSetItem
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.lab_execution import execution_plan
from app.services.certification_versions.runtime import CourseOperation
from app.services.certification_versions.governance_case import load_governance_case
from app.services.certification_versions.governance_inputs import GovernanceInputRepository

pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
repo = enrollment_fixtures.repo


async def fixture(repo, *, enrolled=None):
    if enrolled is None:
        version = enrollment_fixtures.add_scenario_fixture_course(repo)
        folder = repo.catalog.root / version
        draft = CATALOG_ROOT.parent / 'drafts/v5.0'
        (folder / 'governance-cases').mkdir()
        shutil.copyfile(draft / 'governance-capstone-case.json', folder / 'governance-cases/governance.json')
        exercises = json.loads((folder / 'exercises.json').read_text())
        exercises['governance'] = json.loads((draft / 'governance-exercise.json').read_text())
        (folder / 'exercises.json').write_text(json.dumps(exercises))
        for name in exercises['governance']['documents']:
            shutil.copyfile(draft / 'documents' / name, folder / 'documents' / name)
        manifest = json.loads((folder / 'manifest.json').read_text())
        for name in ('governance-cases/governance.json', 'exercises.json', *['documents/' + n for n in exercises['governance']['documents']]):
            manifest['artifacts'][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        registry_path = repo.catalog.root / 'registry.json'
        registry = json.loads(registry_path.read_text())
        registry['releases'][version]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        registry_path.write_text(json.dumps(registry))
        learner = await repo.ensure_initial('governance-learner')
        package = repo.catalog.load(version)
    else:
        learner, package = enrolled
    case = load_governance_case(package)
    documents, content = [], {}
    for assigned in case.sources:
        data = package.read('documents/' + assigned.filename)
        with fitz.open(stream=data, filetype='pdf') as pdf:
            text = '\n\n'.join(page.get_text() for page in pdf)
        path = 'synthetic/' + assigned.filename
        content[path] = data
        documents.append(await SmartDocument(uuid=uuid4().hex, user_id=learner.user_id, title=assigned.filename,
            path=path, downloadpath=path, raw_text=text, folder='governance-lab', processing=False, task_status='completed').insert())
    await repo.progress.update_one({'_id': ObjectId(learner.progress_id)}, {'$set': {
        'lab_folder_id': 'governance-lab', 'modules.governance.provisioned_docs': [d.uuid for d in documents]}})
    artifact = await SearchSet(uuid=uuid4().hex, title='Owned representative extraction', status='active', set_type='extraction', user_id=learner.user_id).insert()
    fields = [await SearchSetItem(searchset=artifact.uuid, user_id=learner.user_id, title=field.title,
        searchphrase=field.meaning, searchtype='extraction', is_optional=False).insert() for field in case.fields]
    body = {'request_id': uuid4().hex, 'artifact_id': artifact.uuid, 'case_sha256': case.digest,
            'consent': 'capture_governance_extraction_and_complete_sources'}
    return SimpleNamespace(learner=learner, package=package, case=case, documents=documents, content=content,
        artifact=artifact, fields=fields, body=body, storage=SimpleNamespace(read=AsyncMock(side_effect=lambda path: content[path])))


async def capture(repo, f, inputs=None, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='capture_governance_inputs') as progress:
        return await (inputs or GovernanceInputRepository()).capture(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.body, actor_user_id=actor or f.learner.user_id, storage=f.storage)


async def test_both_original_sources_and_owned_fields_survive_workspace_deletion(repo):
    f = await fixture(repo)
    saved = await capture(repo, f)
    for source, document in zip(saved['documents'], f.documents):
        assert base64.b64decode(source['source_pdf_base64']) == f.content[document.path]
        assert source['text'] == document.raw_text
        assert source['pages']
        await document.delete()
    await f.artifact.delete()
    for field in f.fields:
        await field.delete()
    f.storage.read.reset_mock()
    assert await capture(repo, f) == saved
    f.storage.read.assert_not_awaited()
    assert await GovernanceInputRepository().get(f.learner.user_id, saved['uuid']) == saved
    assert await GovernanceInputRepository().get('foreign', saved['uuid']) is None
    assert saved['execution_authorized'] is saved['credit_awarded'] is False
    with pytest.raises(EnrollmentConflict, match='not executable'):
        execution_plan(saved, {})
    assert await CertificationLabExecution.get_motor_collection().count_documents({}) == 0
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'foreign_artifact', 'foreign_field', 'foreign_source', 'wrong_folder',
    'wrong_bytes', 'ingestion', 'case', 'consent', 'client_evidence', 'missing_source', 'duplicate_source',
    'wrong_field', 'duplicate_key', 'attached_text', 'source_race', 'artifact_race'])
async def test_invalid_or_racing_inputs_never_create_a_snapshot(repo, monkeypatch, change):
    f = await fixture(repo)
    inputs = GovernanceInputRepository()
    if change == 'foreign_artifact':
        f.artifact.user_id = 'foreign'
        await f.artifact.save()
    elif change == 'foreign_field':
        f.fields[0].user_id = 'foreign'
        await f.fields[0].save()
    elif change in ('foreign_source', 'wrong_folder', 'ingestion'):
        field, value = {'foreign_source': ('user_id', 'foreign'), 'wrong_folder': ('folder', 'other'), 'ingestion': ('processing', True)}[change]
        setattr(f.documents[1], field, value)
        await f.documents[1].save()
    elif change == 'wrong_bytes':
        f.content[f.documents[1].path] = f.content[f.documents[0].path]
    elif change == 'case':
        f.body['case_sha256'] = '0' * 64
    elif change == 'consent':
        f.body['consent'] = 'run_governance'
    elif change == 'client_evidence':
        f.body['passed'] = True
    elif change in ('missing_source', 'duplicate_source'):
        ids = [f.documents[0].uuid] * (1 if change == 'missing_source' else 2)
        await repo.progress.update_one({'_id': ObjectId(f.learner.progress_id)}, {'$set': {'modules.governance.provisioned_docs': ids}})
    elif change in ('wrong_field', 'duplicate_key', 'attached_text'):
        field, value = {'wrong_field': ('title', 'Year 1 only'), 'duplicate_key': ('searchphrase', f.fields[0].searchphrase), 'attached_text': ('text_blocks', ['An unassigned excerpt'])}[change]
        setattr(f.fields[1], field, value)
        await f.fields[1].save()
    elif change == 'source_race':
        async def racing_read(path):
            # The first source changes while the second is being captured.
            if path == f.documents[1].path:
                f.documents[0].raw_text += '\nChanged during the other source read'
                await f.documents[0].save()
            return f.content[path]
        f.storage.read.side_effect = racing_read
    elif change == 'artifact_race':
        original = inputs._read_artifact
        async def racing_artifact(*args):
            value = await original(*args)
            f.fields[0].searchphrase += ' changed'
            await f.fields[0].save()
            return value
        monkeypatch.setattr(inputs, '_read_artifact', racing_artifact)
    with pytest.raises(ValueError):
        await capture(repo, f, inputs, actor='foreign' if change == 'actor' else None)
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('change', ['pdf', 'pages', 'ingestion', 'artifact', 'public_case', 'private_case', 'authority'])
async def test_rehashed_nested_changes_are_not_valid_original_inputs(repo, change):
    f = await fixture(repo)
    saved = deepcopy(await capture(repo, f))
    if change == 'pdf':
        saved['documents'][0]['source_pdf_base64'] = base64.b64encode(f.content[f.documents[1].path]).decode()
    elif change == 'pages':
        saved['documents'][0]['pages'][0] = 'Unrelated page'
    elif change == 'ingestion':
        saved['documents'][0]['text'] = 'Changed ingestion'
    elif change == 'artifact':
        saved['artifact']['fields'][0]['searchphrase'] = 'Changed original instruction'
    elif change == 'public_case':
        saved['case']['task'] = 'Changed public task'
    elif change == 'private_case':
        saved['authored_case']['expectations'][0]['expected_value'] = 'An invented PI'
    else:
        saved['execution_authorized'] = True
    serialized, digest = encode(saved)
    raw = await CertificationLabInput.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw.update(record_json=serialized, record_sha256=digest)
    with pytest.raises(CourseCatalogError):
        GovernanceInputRepository.decode(raw)


async def test_request_reuse_cannot_replace_original_artifact_or_source_set(repo):
    f = await fixture(repo)
    saved = await capture(repo, f)
    f.body['artifact_id'] = uuid4().hex
    with pytest.raises(EnrollmentConflict):
        await capture(repo, f)
    assert await GovernanceInputRepository().get(f.learner.user_id, saved['uuid']) == saved
