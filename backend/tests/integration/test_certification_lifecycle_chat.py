"""Chat in the lifecycle states the panel already covers (QA-10): upgraded, transferring, overridden.

Real chat tools against disposable MongoDB. Each case drives the learner into
the state through the same service the panel uses, then reads and writes
through chat and checks chat reports that state and cannot write past it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_tools
from app.services.certification_versions import readers, runtime
from tests.integration import test_certification_credit_transfer as transfer
from tests.integration import test_certification_enrollments as persisted

repo = persisted.repo
candidate = transfer.candidate
pytestmark = persisted.pytestmark


def chat(user_id):
    return SimpleNamespace(deps=SimpleNamespace(user_id=user_id))


async def test_chat_follows_an_activated_upgrade_and_refuses_the_original_course(repo, candidate, monkeypatch):
    f = await transfer.setup(repo, candidate, monkeypatch, activate=True)
    before = (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json')
    progress = await chat_tools.get_certification_progress(chat(f.user))
    assert progress['enrollment_id'] == f.target.uuid
    assert progress['course_version'] == f.target.course_version != f.source.course_version
    assert progress['total_xp'] == 0 and progress['certified'] is False and progress['modules_completed'] == 0
    lesson = await chat_tools.get_certification_lesson(chat(f.user), 'ai_literacy', 1)
    assert lesson['enrollment_id'] == f.target.uuid and lesson['course_version'] == f.target.course_version
    # A card from before the switch names the original enrollment; chat refuses it and changes nothing.
    stale = await chat_tools.submit_certification_assessment(chat(f.user), 'ai_literacy',
        {'experience': 'Some', 'comfort': 'Some', 'concern': 'Some'}, enrollment_id=f.source.uuid)
    assert 'selected course changed' in stale['error']
    assert (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json') == before
    f.grader.assert_not_awaited()


async def test_chat_reports_transferred_credit_once_and_keeps_the_original(repo, candidate, monkeypatch):
    f = await transfer.setup(repo, candidate, monkeypatch)
    before = (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json')
    result = await f.service.apply(f.user, await transfer.request_for(f))
    base = f.package.manifest.modules[0].base_xp
    for _ in range(2):  # A repeated read, as after a lost reply, changes nothing.
        progress = await chat_tools.get_certification_progress(chat(f.user))
        assert progress['enrollment_id'] == f.target.uuid and progress['total_xp'] == base == result['xp_carried']
        row = next(module for module in progress['modules'] if module['module_id'] == 'ai_literacy')
        assert row['completed'] is True and row['attempts'] == 0
        assert progress['modules_completed'] == 1 and progress['certified'] is False
    module = await chat_tools.get_certification_module(chat(f.user), 'ai_literacy')
    assert module['enrollment_id'] == f.target.uuid
    assert (await repo.read_progress(f.user, f.source.uuid)).model_dump(mode='json') == before
    assert await f.service.journal.records.count_documents({}) == 1
    f.grader.assert_not_awaited()


async def test_chat_after_an_admin_unlock_changes_access_only(repo, monkeypatch):
    from app.routers import admin
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    monkeypatch.setattr(admin, '_require_admin', AsyncMock())
    monkeypatch.setattr(admin, '_audit', AsyncMock())
    learner = await repo.ensure_initial('unlocked-learner')
    before = await chat_tools.get_certification_progress(chat('unlocked-learner'))
    await admin.set_certification_unlock('unlocked-learner', admin.CertificationUnlockRequest(
        unlocked=True, reason='Restore learning access', request_id=uuid4().hex),
        enrollment_id=learner.uuid, user=SimpleNamespace(user_id='administrator'))
    assert (await repo.read_progress('unlocked-learner', learner.uuid)).unlocked is True
    after = await chat_tools.get_certification_progress(chat('unlocked-learner'))
    # The override opens access; it never grants credit, XP or a different next requirement.
    assert after == before
    later = before['modules'][1]['module_id']  # Locked behind its prerequisite until the override.
    module = await chat_tools.get_certification_module(chat('unlocked-learner'), later)
    assert module['enrollment_id'] == learner.uuid
    completion = await chat_tools.complete_certification_module(chat('unlocked-learner'), later,
        enrollment_id=learner.uuid, expected_attempts=0)
    assert not completion.get('xp_earned')
    progress = await repo.read_progress('unlocked-learner', learner.uuid)
    assert progress.total_xp == 0 and not progress.modules.get(later, {}).get('completed')


@pytest.fixture(autouse=True)
def quiet_hooks(monkeypatch):
    monkeypatch.setattr('app.services.certification_service._fire_certification_complete_hooks', AsyncMock())
