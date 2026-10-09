"""Only synthetic credentials and mocked email; no external messages."""
import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.notification import Notification
from app.models.user import User
from app.services.certification_versions.completion_notices import CompletionNoticeRepository, render_email
from app.services.certification_versions.credentials import CredentialRepository, CredentialSnapshot, CompetencyCredentialSnapshot
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark
SETTINGS = SimpleNamespace(promotional_emails_enabled=True, frontend_url='https://example.test')


@pytest.fixture(autouse=True)
def no_external_email(monkeypatch):
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr('app.services.email_service.send_email', sender)
    return sender


async def fixture(*, version='synthetic-outcome-1', modules=('one',), provenance='versioned_course_completion', scope=None):
    model = CompetencyCredentialSnapshot if scope else CredentialSnapshot
    credential = model(credential_id=uuid4().hex, user_id='notice-learner', enrollment_id=uuid4().hex,
        learner_name='Original <Learner>', course_title='Synthetic & scoped course', course_version=version,
        manifest_sha256='a' * 64, rubric_id='synthetic-rubric', provenance=provenance,
        certified_at='2026-10-03T12:00:00+00:00', recorded_at='2026-10-03T12:01:00+00:00',
        level='synthetic', module_ids=modules, evidence=(), outcomes=('outcome-one',),
        **({'credential_scope': scope} if scope else {}))
    await CredentialRepository().persist(credential)
    return credential


async def test_original_and_scoped_credentials_replay_without_changing_notice_identity(repo, no_external_email):
    from app.services.certification_versions.attempts import encode
    notices = CompletionNoticeRepository()
    old = await fixture()
    original_notice = await notices.prepare(old.user_id, old.enrollment_id)
    scope = {'contract_id': 'synthetic-scope', 'contract_sha256': 'b' * 64,
             'promise': 'Original synthetic course promise.', 'agent_assistance': 'Original learner decision rules.',
             'exclusions': ['No institutional approval.']}
    new = await fixture(version='synthetic-scoped-2', scope=scope)
    scoped_notice = await notices.prepare(new.user_id, new.enrollment_id)
    for record, prepared in [(old, original_notice), (new, scoped_notice)]:
        reread = await CredentialRepository().get(record.user_id, record.credential_id)
        assert reread.model_dump(mode='json') == record.model_dump(mode='json')
        assert notices.decode(prepared)['credential_sha256'] == encode(record.model_dump(mode='json'))[1]
        repeated = await notices.prepare(record.user_id, record.enrollment_id)
        assert repeated['record_json'] == prepared['record_json']
        assert repeated['record_sha256'] == prepared['record_sha256']
    assert await notices.records.count_documents({}) == 2
    no_external_email.assert_not_awaited()


async def user():
    value = User(user_id='notice-learner', name='Current name', email='learner@example.test',
        certification_complete_sent_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
    await value.insert()
    return value


async def test_concurrent_notice_replay_keeps_one_original_message_even_after_read_or_delete(repo, no_external_email):
    credential = await fixture()
    notices = CompletionNoticeRepository()
    rows = await asyncio.gather(*(notices.prepare(credential.user_id, credential.enrollment_id) for _ in range(5)))
    await asyncio.gather(*(notices.notify(row) for row in rows))
    assert await notices.records.count_documents({}) == 1
    assert await Notification.get_motor_collection().count_documents({}) == 1
    original = await Notification.get_motor_collection().find_one({})
    assert '1 required module completed' in original['body']
    assert 'synthetic-outcome-1' in original['body'] and '2026-10-03' in original['body']
    assert '11' not in original['body'] and '1,600' not in original['body'] and 'publish' not in original['body']
    await Notification.get_motor_collection().update_one({'_id': original['_id']}, {'$set': {'read': True}})
    await notices.notify(await notices.prepare(credential.user_id, credential.enrollment_id))
    assert (await Notification.get_motor_collection().find_one({}))['read'] is True
    await Notification.get_motor_collection().delete_one({'_id': original['_id']})
    await notices.notify(await notices.prepare(credential.user_id, credential.enrollment_id))
    assert await Notification.get_motor_collection().count_documents({}) == 0
    no_external_email.assert_not_called()


async def test_lost_notification_insert_reply_reuses_same_row(repo, monkeypatch):
    credential = await fixture()
    notices = CompletionNoticeRepository()
    raw = await notices.prepare(credential.user_id, credential.enrollment_id)
    collection = Notification.get_motor_collection()
    update = collection.update_one
    async def lost(*args, **kwargs):
        await update(*args, **kwargs)
        raise RuntimeError('Synthetic lost insert reply')
    with monkeypatch.context() as patch:
        patch.setattr(collection, 'update_one', lost)
        with pytest.raises(RuntimeError, match='lost insert'):
            await notices.notify(raw)
    await notices.notify(await notices.prepare(credential.user_id, credential.enrollment_id))
    assert await collection.count_documents({}) == 1


async def test_later_credential_gets_its_own_email_once_despite_legacy_user_flag(repo, no_external_email):
    owner = await user()
    timestamp = owner.certification_complete_sent_at
    notices = CompletionNoticeRepository()
    for version, modules in [('first', ('a',)), ('second', ('a', 'b'))]:
        credential = await fixture(version=version, modules=modules)
        raw = await notices.prepare(credential.user_id, credential.enrollment_id)
        results = await asyncio.gather(*(notices.email(raw, owner, SETTINGS) for _ in range(5)))
        assert results.count(True) == 1
        assert await notices.email(await notices.prepare(owner.user_id, credential.enrollment_id), owner, SETTINGS) is False
    assert no_external_email.await_count == 2
    messages = [call.args[2] for call in no_external_email.await_args_list]
    assert '1 required module completed' in messages[0] and '2 required modules completed' in messages[1]
    assert 'Original &lt;Learner&gt;' in messages[0] and 'Synthetic &amp; scoped course' in messages[0]
    assert 'https://example.test/certification' in messages[0]
    assert 'Manage email preferences' in messages[0]
    latest = await User.find_one(User.user_id == owner.user_id)
    assert latest.certification_complete_sent_at.replace(tzinfo=datetime.timezone.utc) == timestamp
    assert latest.last_marketing_email_at is not None


@pytest.mark.parametrize('failure', ['false', 'exception', 'cancelled', 'lost_claim'])
async def test_ambiguous_email_is_never_automatically_repeated(repo, monkeypatch, no_external_email, failure):
    owner = await user()
    credential = await fixture()
    notices = CompletionNoticeRepository()
    raw = await notices.prepare(owner.user_id, credential.enrollment_id)
    if failure == 'false':
        no_external_email.return_value = False
        assert await notices.email(raw, owner, SETTINGS) is False
    elif failure == 'lost_claim':
        update = notices.records.update_one
        async def lost(*args, **kwargs):
            await update(*args, **kwargs)
            raise RuntimeError('Synthetic lost send claim reply')
        with monkeypatch.context() as patch:
            patch.setattr(notices.records, 'update_one', lost)
            with pytest.raises(RuntimeError):
                await notices.email(raw, owner, SETTINGS)
    else:
        error = RuntimeError('Synthetic provider lost acknowledgement') if failure == 'exception' else asyncio.CancelledError()
        no_external_email.side_effect = error
        with pytest.raises(type(error)):
            await notices.email(raw, owner, SETTINGS)
    saved = await notices.prepare(owner.user_id, credential.enrollment_id)
    assert saved['email_state'] in ('uncertain', 'sending')
    count = no_external_email.await_count
    assert await notices.email(saved, owner, SETTINGS) is False
    assert no_external_email.await_count == count
    await notices.notify(saved)
    assert await Notification.get_motor_collection().count_documents({}) == 1


async def test_preferences_disabled_delivery_and_ownership_gate_precede_any_send(repo, no_external_email):
    owner = await user()
    credential = await fixture()
    notices = CompletionNoticeRepository()
    raw = await notices.prepare(owner.user_id, credential.enrollment_id)
    with pytest.raises(EnrollmentConflict):
        await notices.prepare('foreign', credential.enrollment_id)
    with pytest.raises(EnrollmentConflict):
        await notices.email(raw, SimpleNamespace(user_id='foreign'), SETTINGS)
    disabled = SimpleNamespace(promotional_emails_enabled=False)
    assert await notices.email(raw, owner, disabled) is False
    assert (await notices.records.find_one({}))['email_state'] == 'pending'
    owner.email_preferences = {'announcements': False}
    assert await notices.email(raw, owner, SETTINGS) is False
    assert (await notices.records.find_one({}))['email_state'] == 'skipped'
    no_external_email.assert_not_called()


async def test_original_payload_cannot_change_with_profile_or_catalog_and_corruption_fails_closed(repo, no_external_email):
    owner = await user()
    credential = await fixture()
    notices = CompletionNoticeRepository()
    raw = await notices.prepare(owner.user_id, credential.enrollment_id)
    await User.get_motor_collection().update_one({'user_id': owner.user_id}, {'$set': {'name': 'Later profile name'}})
    assert (await notices.prepare(owner.user_id, credential.enrollment_id))['record_json'] == raw['record_json']
    await notices.records.update_one({'uuid': credential.credential_id}, {'$set': {'record_json': raw['record_json'] + ' '}})
    with pytest.raises(CourseCatalogError):
        await notices.prepare(owner.user_id, credential.enrollment_id)
    no_external_email.assert_not_called()


async def test_historical_preservation_is_not_announced_as_a_new_completion(repo, no_external_email):
    credential = await fixture(provenance='legacy_completion_unverified')
    with pytest.raises(EnrollmentConflict, match='Historical'):
        await CompletionNoticeRepository().prepare(credential.user_id, credential.enrollment_id)
    assert await CompletionNoticeRepository().records.count_documents({}) == 0
    no_external_email.assert_not_called()


async def test_email_rejects_non_application_link_before_send_claim(repo, no_external_email):
    credential = await fixture()
    raw = await CompletionNoticeRepository().prepare(credential.user_id, credential.enrollment_id)
    with pytest.raises(ValueError):
        render_email(CompletionNoticeRepository.decode(raw), 'javascript:alert(1)')
    no_external_email.assert_not_called()


async def test_real_completion_retries_recover_notice_after_a_lost_insert_reply(repo, monkeypatch, no_external_email):
    from app.services import certification_service
    from tests.integration import test_certification_outcome_completion as completion
    original_hook = certification_service._fire_certification_complete_hooks
    f, client, _, body, _, judge = await completion.setup(repo, monkeypatch, single_module=True)
    monkeypatch.setattr(certification_service, '_fire_certification_complete_hooks', original_hook)
    notices = CompletionNoticeRepository()
    original_notify = CompletionNoticeRepository.notify
    calls = 0
    async def lost(self, raw):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('Synthetic notification write unavailable')
        return await original_notify(self, raw)
    monkeypatch.setattr(CompletionNoticeRepository, 'notify', lost)
    params = {'enrollment_id': f.learner.uuid, 'request_id': uuid4().hex}
    async with client:
        first = await client.post('/certification/modules/validation_qa/complete', params=params, json=body)
        assert first.status_code == 200, first.text
        assert await notices.records.count_documents({}) == 1
        assert await Notification.get_motor_collection().count_documents({}) == 0
        again = await client.post('/certification/modules/validation_qa/complete', params=params)
        assert again.status_code == 200 and again.json() == first.json()
        assert await Notification.get_motor_collection().count_documents({}) == 1
        assert '1 required module completed' in (await Notification.get_motor_collection().find_one({}))['body']
        assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == first.json()['xp_earned']
    judge.assert_awaited_once()
    no_external_email.assert_not_called()  # No profile recipient in this isolated completion fixture.
