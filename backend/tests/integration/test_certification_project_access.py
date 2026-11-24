"""New captures must respect project access as well as document ownership."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.certification import CertificationLabInput, CertificationProgress
from app.models.folder import SmartFolder
from app.models.project import Project, ProjectMembership
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.services.access_control import get_authorized_document, TeamAccessContext
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.source_access import owned_source
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = base.pytestmark


async def project_lab(learner, document, grant='none'):
    root = 'project-root'
    await SmartFolder(uuid=root, title='Project root', parent_id='0', user_id='other-owner').insert()
    await SmartFolder(uuid=document.folder, title='Certification Lab', parent_id=root, user_id=learner.user_id).insert()
    project = await Project(uuid='private-project', title='Project', owner_user_id=learner.user_id if grant == 'owner' else 'other-owner', root_folder_uuid=root).insert()
    membership = None
    if grant in ('viewer', 'editor'):
        membership = await ProjectMembership(project_uuid=project.uuid, user_id=learner.user_id, role=grant).insert()
    elif grant == 'team':
        team = await Team(uuid='project-team', name='Project team', owner_user_id='other-owner').insert()
        project.team_id = team.uuid
        await project.save()
        membership = await TeamMembership(team=team.id, user_id=learner.user_id).insert()
    return project, membership


async def test_owned_assigned_document_in_an_inaccessible_project_cannot_be_captured(repo):
    learner, package, document, artifact, _, storage = await base.make_lab_input_fixture(repo)
    await SmartFolder(uuid=document.folder, title='Moved training lab', parent_id='0', user_id=learner.user_id).insert()
    await Project(uuid='private-project', title='Another owner project', owner_user_id='other-owner', root_folder_uuid=document.folder).insert()
    assert await get_authorized_document(document.uuid, User(user_id=learner.user_id), team_access=TeamAccessContext()) is None
    with pytest.raises(EnrollmentConflict):
        await base.capture_lab(repo, learner, package, artifact.uuid, storage)
    storage.read.assert_not_awaited()
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


@pytest.mark.parametrize('grant', ['owner', 'viewer', 'editor', 'team'])
async def test_authorized_owned_sources_remain_available_for_read_only_capture(repo, grant):
    learner, package, document, artifact, _, storage = await base.make_lab_input_fixture(repo)
    await project_lab(learner, document, grant)
    saved = await base.capture_lab(repo, learner, package, artifact.uuid, storage)
    assert saved['documents'][0]['document_id'] == document.uuid
    assert saved['documents'][0]['text'] == document.raw_text
    assert (await repo.read_progress(learner.user_id, learner.uuid)).total_xp == 0


@pytest.mark.parametrize('grant', ['viewer', 'team'])
async def test_revocation_during_source_read_prevents_new_evidence(repo, grant):
    learner, package, document, artifact, _, storage = await base.make_lab_input_fixture(repo)
    _, membership = await project_lab(learner, document, grant)
    async def revoke(path):
        await membership.delete()
        return package.read('documents/nsf-proposal-alpine-ecology.pdf')
    storage.read.side_effect = revoke
    with pytest.raises(EnrollmentConflict):
        await base.capture_lab(repo, learner, package, artifact.uuid, storage)
    storage.read.assert_awaited_once()
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0


async def test_revocation_blocks_new_capture_but_keeps_original_authorized_snapshot(repo):
    learner, package, document, artifact, _, storage = await base.make_lab_input_fixture(repo)
    _, membership = await project_lab(learner, document, 'viewer')
    request_id = uuid4().hex
    original = await base.capture_lab(repo, learner, package, artifact.uuid, storage, request_id)
    await membership.delete()
    storage.read.reset_mock()
    assert await owned_source(learner.user_id, document.uuid) is None
    with pytest.raises(EnrollmentConflict):
        await base.capture_lab(repo, learner, package, artifact.uuid, storage)
    assert await base.capture_lab(repo, learner, package, artifact.uuid, storage, request_id) == original
    storage.read.assert_not_awaited()
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 1


@pytest.mark.parametrize('change', ['transferred', 'deleted', 'wrong_lab'])
async def test_project_read_access_cannot_replace_source_ownership_and_lab_binding(repo, change):
    learner, _, document, _, _, _ = await base.make_lab_input_fixture(repo)
    await project_lab(learner, document, 'viewer')
    if change == 'transferred':
        document.user_id = 'other-owner'
    elif change == 'deleted':
        document.soft_deleted = True
    await document.save()
    assert await owned_source(learner.user_id, document.uuid,
                              lab_folder_id='different-lab' if change == 'wrong_lab' else document.folder) is None


async def test_live_assigned_source_delivery_hides_revoked_project_text_but_preserves_saved_history(repo):
    from app.services.certification_versions.advanced_workflow_delivery import AdvancedWorkflowDelivery
    from tests.integration import test_certification_advanced_calculation_records as calculations
    f = await calculations.fixture(repo)
    _, membership = await project_lab(f.learner, f.document, 'viewer')
    saved = await calculations.submit(repo, f)
    delivery = AdvancedWorkflowDelivery(repo)
    visible = await delivery.list(f.learner.user_id, f.learner.uuid, delivery_enabled=True)
    assert visible['assigned_sources'][0]['text'] == f.document.raw_text
    await membership.delete()
    hidden = await delivery.list(f.learner.user_id, f.learner.uuid, delivery_enabled=True)
    assert hidden['assigned_sources'] == []
    assert hidden['calculations'] == visible['calculations']
    assert await delivery.calculations.get(f.learner.user_id, saved['uuid']) == saved


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('grant', ['none', 'viewer'])
async def test_provisioning_requires_contribution_access_to_the_project(versioned_runtime, monkeypatch, versioned, grant):
    from app.services import certification_service, file_service, folder_service
    from app.services.certification_versions import runtime
    repo = versioned_runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, document, _, _, _ = await base.make_lab_input_fixture(repo)
    await project_lab(learner, document, grant)
    upload, create = AsyncMock(), AsyncMock()
    monkeypatch.setattr(file_service, 'upload_document', upload)
    monkeypatch.setattr(folder_service, 'create_folder', create)
    before = await repo.progress.find_one({'user_id': learner.user_id})
    with pytest.raises(EnrollmentConflict, match='no longer accessible'):
        await certification_service.provision_module_documents(User(user_id=learner.user_id), 'foundations', {}, enrollment_id=learner.uuid if versioned else None)
    after = await repo.progress.find_one({'user_id': learner.user_id})
    for item in (before, after):
        item.pop('_certification_write_fence', None)
    assert after == before
    upload.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.parametrize('versioned', [False, True])
@pytest.mark.parametrize('grant', ['owner', 'editor', 'team'])
async def test_provisioning_reuses_owned_sources_in_a_permitted_project(versioned_runtime, monkeypatch, versioned, grant):
    from app.services import certification_service, file_service, folder_service
    from app.services.certification_versions import runtime
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: versioned)
    learner, _, document, _, _, _ = await base.make_lab_input_fixture(versioned_runtime)
    if not versioned:
        # Model an actual pre-initialization learner, not a versioned record
        # with its runtime disabled (which correctly refuses unfenced writes).
        await CertificationProgress.get_motor_collection().update_one(
            {'user_id': learner.user_id}, {'$unset': {'enrollment_id': '', 'course_version': ''}})
    await project_lab(learner, document, grant)
    upload, create = AsyncMock(), AsyncMock()
    monkeypatch.setattr(file_service, 'upload_document', upload)
    monkeypatch.setattr(folder_service, 'create_folder', create)
    result = await certification_service.provision_module_documents(
        User(user_id=learner.user_id), 'foundations', {}, enrollment_id=learner.uuid if versioned else None)
    assert result['provisioned_docs'] == [document.uuid]
    upload.assert_not_awaited()
    create.assert_not_awaited()
