"""A Save decision executes exactly the stored page, without regenerating HTML."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services import artifacts, chat_page_previews as previews
from app.services.chat_page_approval import stream_save
from app.services.chat_stream_transport import with_heartbeats
from tests.test_artifacts import Collection


@pytest.fixture
def db():
    return SimpleNamespace(html_artifacts=Collection(), chat_page_previews=Collection())


def proposal(db, html=None, doc=None):
    # Roughly 200 KiB: well beyond a typical model's single-call output cap.
    html = html or '<table>' + ''.join(f'<tr><td>{i}</td><td>Agency requirement {i}</td></tr>' for i in range(4000)) + '</table>'
    return previews.prepare(db, 'owner', 'chat', 'NIH dashboard', html,
        doc['uuid'] if doc else None, doc['latest_revision'] if doc else None, {'kind': 'chat'})


def test_large_revision_saves_exact_preview_on_first_approval(db):
    doc = artifacts.create(db, 'owner', 'Old', '<p>Old dashboard</p>', 'original')
    preview = proposal(db, doc=doc)
    assert len(preview['html']) > 100000
    saved = previews.save(db, 'owner', 'chat', preview['_id'])
    page = artifacts.get(db, doc['uuid'])
    assert len(page['revisions']) == 2
    assert artifacts.revision(page)['html'] == preview['prepared_html']
    assert saved['revision'] == page['latest_revision']
    assert saved['version'] == 2
    assert saved['message'] == 'Saved "NIH dashboard" as Page version 2.'


@pytest.mark.parametrize('revision', [False, True])
def test_lost_acknowledgement_retry_never_creates_another_page_or_version(db, revision):
    doc = artifacts.create(db, 'owner', 'Old', '<p>Old</p>', 'original') if revision else None
    preview = proposal(db, '<p>Reviewed</p><script>removed()</script>', doc)
    first = previews.save(db, 'owner', 'chat', preview['_id'])
    assert first['version'] == (2 if revision else 1)
    for _ in range(3):
        assert previews.save(db, 'owner', 'chat', preview['_id']) == first
    assert len(db.html_artifacts.docs) == 1
    page = artifacts.get(db, first['artifact_uuid'])
    assert len(page['revisions']) == (2 if revision else 1)
    assert first['warnings'] == preview['warnings']
    later = artifacts.revise(db, page, 'Later', '<p>A later edit</p>', first['revision'])
    assert previews.save(db, 'owner', 'chat', preview['_id']) == first
    assert artifacts.get(db, page['uuid'])['latest_revision'] == later['latest_revision']


def test_stale_preview_never_overwrites_another_edit(db):
    doc = artifacts.create(db, 'owner', 'Old', '<p>Old</p>', 'original')
    preview = proposal(db, '<p>Proposal</p>', doc)
    newer = artifacts.revise(db, doc, 'Newer', '<p>Someone edited</p>', doc['latest_revision'])
    with pytest.raises(HTTPException) as error:
        previews.save(db, 'owner', 'chat', preview['_id'])
    assert error.value.status_code == 409
    assert artifacts.get(db, doc['uuid'])['latest_revision'] == newer['latest_revision']
    assert len(artifacts.get(db, doc['uuid'])['revisions']) == 2


def test_identical_concurrent_revision_returns_the_winners_version(db):
    original = artifacts.create(db, 'owner', 'Old', '<p>Old</p>', 'original')
    winner = artifacts.revise(db, original, 'Reviewed', '<p>Approved</p>', original['latest_revision'])
    # A second writer still holds the original read, so its CAS loses.
    second = artifacts.revise(db, original, 'Reviewed', '<p>Approved</p>', original['latest_revision'])
    assert second['latest_revision'] == winner['latest_revision']
    assert len(second['revisions']) == 2


@pytest.mark.parametrize(('user', 'conversation'), [('stranger', 'chat'), ('owner', 'another-chat')])
def test_preview_is_bound_to_owner_and_conversation(db, user, conversation):
    preview = proposal(db, '<p>Private</p>')
    with pytest.raises(HTTPException) as error:
        previews.save(db, user, conversation, preview['_id'])
    assert error.value.status_code == 404
    assert not db.html_artifacts.docs


@pytest.mark.asyncio
async def test_save_stream_persists_result_before_reporting_success_and_has_no_new_approval(db):
    preview = proposal(db)
    conversation = SimpleNamespace(uuid='chat', pending_confirmations=[])
    finalized = AsyncMock()
    with (
        patch('app.services.chat_artifact_tools.get_sync_db', return_value=db),
        patch('app.services.chat_service._finalize', finalized),
        patch('app.services.chat_service.create_agentic_chat_agent', side_effect=AssertionError('Must not generate HTML again')),
    ):
        stream = stream_save(conversation, preview, 'activity', 'owner')
        call = json.loads(await anext(stream))
        assert call['kind'] == 'tool_call'
        assert call['args'] == {'preview_id': preview['_id'], 'title': 'NIH dashboard', 'confirmed': True}
        result = json.loads(await anext(stream))
        finalized.assert_awaited_once()
        assert result['kind'] == 'tool_result'
        assert result['content']['preview_id'] == preview['_id']
        assert 'needs_confirmation' not in result['content']
        receipt = json.loads(await anext(stream))
        assert receipt == {'kind': 'text', 'content': 'Saved "NIH dashboard" as Page version 1.'}
        assert result['content']['revision'] not in receipt['content']
        assert result['content']['artifact_uuid'] not in receipt['content']
        await stream.aclose()
    assert finalized.await_args.kwargs['tool_results'][0]['content'] == result['content']


@pytest.mark.asyncio
async def test_save_conflict_is_a_persisted_actionable_error_not_another_preview(db):
    doc = artifacts.create(db, 'owner', 'Old', '<p>Old</p>', 'original')
    preview = proposal(db, '<p>Proposal</p>', doc)
    artifacts.revise(db, doc, 'Newer', '<p>Newer</p>', doc['latest_revision'])
    failed = AsyncMock()
    with (
        patch('app.services.chat_artifact_tools.get_sync_db', return_value=db),
        patch('app.services.chat_service._save_failed_assistant_turn', failed),
    ):
        chunks = [json.loads(chunk) async for chunk in stream_save(SimpleNamespace(uuid='chat'), preview, 'activity', 'owner')]
    assert chunks[-1]['kind'] == 'error'
    assert 'changed' in chunks[-1]['content']
    assert not any(chunk.get('content', {}).get('needs_confirmation') for chunk in chunks if isinstance(chunk.get('content'), dict))
    failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_during_save_finishes_the_version_and_records_its_receipt(db):
    preview = proposal(db, '<p>Approved snapshot</p>')
    started, release = asyncio.Event(), asyncio.Event()
    finalized = AsyncMock()

    async def delayed_save(fn, *args):
        started.set()
        await release.wait()
        return fn(db, *args)

    with (
        patch('app.services.chat_page_approval._call', side_effect=delayed_save),
        patch('app.services.chat_service._finalize', finalized),
    ):
        stream = with_heartbeats(stream_save(SimpleNamespace(uuid='chat', pending_confirmations=[]), preview, 'activity', 'owner'))
        assert json.loads(await anext(stream))['kind'] == 'tool_call'
        pending = asyncio.create_task(anext(stream))
        await asyncio.wait_for(started.wait(), timeout=2)
        pending.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, timeout=2)
        finalized.assert_awaited_once()
    receipt = finalized.await_args.kwargs['tool_results'][0]['content']
    assert previews.save(db, 'owner', 'chat', preview['_id']) == receipt
    assert len(db.html_artifacts.docs) == 1


def test_unconfirmed_preview_upsert_reports_retryable_failure_and_reuses_identity(db, monkeypatch):
    original = db.chat_page_previews.find_one_and_update

    def lost_reply(*args, **kwargs):
        original(*args, **kwargs)
        return None

    with monkeypatch.context() as patcher:
        patcher.setattr(db.chat_page_previews, 'find_one_and_update', lost_reply)
        with pytest.raises(HTTPException) as error:
            proposal(db, '<p>Exact reviewed content</p>')
    assert error.value.status_code == 503
    assert len(db.chat_page_previews.docs) == 1
    retried = proposal(db, '<p>Exact reviewed content</p>')
    assert retried['_id'] == db.chat_page_previews.docs[0]['_id']
    assert len(db.chat_page_previews.docs) == 1
    assert not db.html_artifacts.docs
