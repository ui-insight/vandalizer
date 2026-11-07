"""A sample upload cannot commit an assignment after its access is revoked."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.document import SmartDocument
from app.models.user import User
from app.services import certification_service, file_service
from app.services.certification_versions import runtime
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base
from tests.integration.test_certification_project_access import project_lab

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('change', ['revoked', 'viewer', 'moved', 'deleted', 'transferred', 'renamed'])
async def test_access_change_during_upload_does_not_assign_the_result(versioned_runtime, monkeypatch, versioned, change):
    repository = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, original, _, _, _ = await base.make_lab_input_fixture(repository)
    folder_id = original.folder
    _, membership = await project_lab(learner, original, 'editor')
    # Keep previous work intact but make the assigned filename need an upload.
    original.title = 'previous-work.pdf'
    await original.save()
    if not versioned:
        await repository.progress.update_one({'user_id': learner.user_id}, {'$unset': {'enrollment_id': '', 'course_version': ''}})
    before = await repository.progress.find_one({'user_id': learner.user_id})

    async def upload(**kwargs):
        assert kwargs['folder'] == folder_id
        document = await SmartDocument(uuid=uuid4().hex, title=kwargs['filename'], user_id=learner.user_id,
            path='synthetic/upload.pdf', downloadpath='synthetic/upload.pdf', folder=folder_id,
            processing=True, task_status='extracting').insert()
        if change == 'revoked':
            await membership.delete()
        elif change == 'viewer':
            membership.role = 'viewer'
            await membership.save()
        else:
            if change == 'moved':
                document.folder = 'another-folder'
            elif change == 'deleted':
                document.soft_deleted = True
            elif change == 'transferred':
                document.user_id = 'another-owner'
            else:
                document.title = 'different-sample.pdf'
            await document.save()
        return {'uuid': document.uuid}

    dispatch = AsyncMock(side_effect=upload)
    monkeypatch.setattr(file_service, 'upload_document', dispatch)
    with pytest.raises(EnrollmentConflict, match='no longer accessible'):
        await certification_service.provision_module_documents(User(user_id=learner.user_id), 'foundations', {},
            enrollment_id=learner.uuid if versioned else None)
    dispatch.assert_awaited_once()
    after = await repository.progress.find_one({'user_id': learner.user_id})
    for value in (before, after):
        value.pop('_certification_write_fence', None)
    assert after == before
    assert await SmartDocument.find_one(SmartDocument.uuid == original.uuid) is not None


@pytest.mark.parametrize('versioned', [False, True])
async def test_later_upload_cannot_hide_revocation_of_an_earlier_reused_sample(versioned_runtime, monkeypatch, versioned):
    repository = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, original, _, _, _ = await base.make_lab_input_fixture(repository)
    await project_lab(learner, original, 'editor')
    original.title = 'proposal-batch-1.pdf'
    await original.save()
    if not versioned:
        await repository.progress.update_one({'user_id': learner.user_id}, {'$unset': {'enrollment_id': '', 'course_version': ''}})
    before = await repository.progress.find_one({'user_id': learner.user_id})

    async def upload(**kwargs):
        document = await SmartDocument(uuid=uuid4().hex, title=kwargs['filename'], user_id=learner.user_id,
            path='synthetic/batch.pdf', downloadpath='synthetic/batch.pdf', folder=original.folder,
            processing=True, task_status='extracting').insert()
        original.soft_deleted = True
        await original.save()
        return {'uuid': document.uuid}

    dispatch = AsyncMock(side_effect=upload)
    monkeypatch.setattr(file_service, 'upload_document', dispatch)
    with pytest.raises(EnrollmentConflict, match='no longer accessible'):
        await certification_service.provision_module_documents(User(user_id=learner.user_id), 'batch_processing', {},
            enrollment_id=learner.uuid if versioned else None)
    assert dispatch.await_count == 2
    after = await repository.progress.find_one({'user_id': learner.user_id})
    for value in (before, after):
        value.pop('_certification_write_fence', None)
    assert after == before
