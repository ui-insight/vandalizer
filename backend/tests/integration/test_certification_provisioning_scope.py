"""Lab setup must never borrow an unrelated same-named workspace document."""
from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.user import User
from app.services import certification_service, file_service, folder_service
from app.services.certification_versions import runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('existing_lab_source', [False, True])
async def test_same_filename_elsewhere_is_not_a_lab_source(
    versioned_runtime, monkeypatch, versioned, existing_lab_source,
):
    repository = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, unrelated, _, _, _ = await base.make_lab_input_fixture(repository)
    lab_id = unrelated.folder
    unrelated.folder = 'unrelated-private-folder'
    unrelated.raw_text = 'My unrelated private work, not a course sample.'
    await unrelated.save()
    await SmartFolder(uuid=unrelated.folder, title='Private work', parent_id='0', user_id=learner.user_id).insert()
    await SmartFolder(uuid=lab_id, title='Certification Lab', parent_id='0', user_id=learner.user_id).insert()
    if not versioned:
        await repository.progress.update_one({'user_id': learner.user_id}, {
            '$unset': {'enrollment_id': '', 'course_version': ''},
        })
    before = await SmartDocument.get_motor_collection().find_one({'_id': unrelated.id})
    lab_uuid = uuid4().hex
    if existing_lab_source:
        await SmartDocument(uuid=lab_uuid, user_id=learner.user_id, title=unrelated.title,
                            path='synthetic/lab.pdf', downloadpath='synthetic/lab.pdf',
                            folder=lab_id, raw_text='Course sample').insert()
    async def upload_sample(**kwargs):
        await SmartDocument(uuid=lab_uuid, user_id=learner.user_id, title=kwargs['filename'],
                            path='synthetic/lab.pdf', downloadpath='synthetic/lab.pdf',
                            folder=kwargs['folder'], processing=True, task_status='extracting').insert()
        return {'uuid': lab_uuid}
    upload = AsyncMock(side_effect=upload_sample)
    create = AsyncMock()
    monkeypatch.setattr(file_service, 'upload_document', upload)
    monkeypatch.setattr(folder_service, 'create_folder', create)

    result = await certification_service.provision_module_documents(
        User(user_id=learner.user_id), 'foundations', {},
        enrollment_id=learner.uuid if versioned else None,
    )

    assert result['provisioned_docs'] == [lab_uuid]
    saved = await repository.progress.find_one({'user_id': learner.user_id})
    assert saved['modules']['foundations']['provisioned_docs'] == [lab_uuid]
    assert await SmartDocument.get_motor_collection().find_one({'_id': unrelated.id}) == before
    create.assert_not_awaited()
    if existing_lab_source:
        upload.assert_not_awaited()
    else:
        upload.assert_awaited_once()
        assert upload.await_args.kwargs['folder'] == lab_id
        assert upload.await_args.kwargs['filename'] == unrelated.title


@pytest.mark.parametrize('progress_state', ['pinned', 'fenced', 'ambiguous'])
@pytest.mark.parametrize('existing_folder', [False, True])
async def test_disabled_versioning_rejects_pinned_progress_before_external_setup(versioned_runtime, monkeypatch, progress_state, existing_folder):
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    learner = await versioned_runtime.ensure_initial('pinned-before-upload')
    if progress_state != 'pinned':
        await versioned_runtime.progress.update_one({'user_id': learner.user_id}, {
            '$unset': {'enrollment_id': '', 'course_version': ''},
            **({'$set': {'_certification_write_fence': 'another-worker'}} if progress_state == 'fenced' else {}),
        })
    if progress_state == 'ambiguous':
        duplicate = await versioned_runtime.progress.find_one({'user_id': learner.user_id})
        duplicate.pop('_id')
        await versioned_runtime.progress.insert_one(duplicate)
    if existing_folder:
        await SmartFolder(uuid='existing-folder', title='Certification Lab', user_id=learner.user_id, parent_id='0').insert()
    create = AsyncMock(return_value=SimpleNamespace(uuid='would-create-folder'))
    upload = AsyncMock(return_value={'uuid': 'would-upload-sample'})
    monkeypatch.setattr(folder_service, 'create_folder', create)
    monkeypatch.setattr(file_service, 'upload_document', upload)
    before = await versioned_runtime.progress.find_one({'user_id': learner.user_id})
    with pytest.raises(EnrollmentConflict, match='enrollment write boundary|ambiguous'):
        await certification_service.provision_module_documents(User(user_id=learner.user_id), 'foundations', {})
    assert await versioned_runtime.progress.find_one({'user_id': learner.user_id}) == before
    create.assert_not_awaited()
    upload.assert_not_awaited()
