"""Transcript saves survive reopening, without merging distinct snapshots."""
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.schemas.artifact import ChatArtifactRequest
from app.services import artifacts, transcript_pages
from tests.test_artifacts import db as db, route_env as route_env
from tests.test_chat_routes import _auth


def request(request_id='first-click', conversation='nih-chat', **changes):
    return ChatArtifactRequest(**{
        'request_id': request_id, 'conversation_uuid': conversation,
        'messages': [
            {'role': 'user', 'content': 'What is the total subaward amount and period of performance?'},
            {'role': 'assistant', 'content': 'Total: $120,000.', 'evidence': 'Award.pdf · p. 3'},
        ], **changes,
    })


@pytest.mark.asyncio
async def test_reopened_conversation_reuses_one_named_private_page(client, db, route_env):
    cookies, headers = _auth()
    title = 'Chatting About NIH Subaward Document'
    conversation = SimpleNamespace(uuid='nih-chat', title=title)
    with patch('app.models.chat.ChatConversation.find_one', AsyncMock(return_value=conversation)) as lookup:
        responses = []
        for attempt in range(4):
            response = await client.post('/api/pages/from-chat', json=request(f'reopened-{attempt}').model_dump(), cookies=cookies, headers=headers)
            assert response.status_code == 200
            responses.append(response.json())
        assert len({item['uuid'] for item in responses}) == 1
        assert [item['reused'] for item in responses] == [False, True, True, True]
        assert all(item['title'] == title and item['source']['kind'] == 'chat_export' for item in responses)
        assert len(db.html_artifacts.docs) == 1
        saved = db.html_artifacts.docs[0]
        assert not saved['public_token'] and not saved['team_id']
        html = BeautifulSoup(artifacts.revision(saved)['html'], 'html.parser')
        assert html.h1.text == html.title.text == title
        assert '$120,000' in html.text and 'Award.pdf · p. 3' in html.text
        lookup.assert_awaited_with({'uuid': 'nih-chat', 'user_id': 'testuser'})
        # Even a known snapshot remains inaccessible after source authorization fails.
        lookup.return_value = None
        denied = await client.post('/api/pages/from-chat', json=request('another-click').model_dump(), cookies=cookies, headers=headers)
        assert denied.status_code == 404
        assert len(db.html_artifacts.docs) == 1


def test_changed_content_evidence_conversation_and_owner_are_distinct(db):
    first, _ = transcript_pages.save(db, 'owner', request(), 'NIH award')
    changed = request()
    changed.messages.append(changed.messages[0].model_copy(update={'content': 'List the reporting deadlines.'}))
    other, _ = transcript_pages.save(db, 'owner', changed, 'NIH award')
    evidence = request()
    evidence.messages[1].evidence = 'Award.pdf · p. 4'
    corrected, _ = transcript_pages.save(db, 'owner', evidence, 'NIH award')
    another_chat, _ = transcript_pages.save(db, 'owner', request(conversation='another-chat'), 'NIH award')
    another_owner, _ = transcript_pages.save(db, 'other-owner', request(), 'NIH award')
    selected, _ = transcript_pages.save(db, 'owner', request(messages=[request().messages[1]]), 'NIH award')
    assert len({doc['uuid'] for doc in [first, other, corrected, another_chat, another_owner, selected]}) == 6


def test_reuse_preserves_page_edits_renames_publication_and_original_heading(db):
    first, _ = transcript_pages.save(db, 'owner', request(), 'Original conversation name')
    shared = artifacts.publish(db, first, first['latest_revision'])
    edited = artifacts.revise(db, shared, 'Edited report', '<p>Reviewed text</p>', shared['latest_revision'])
    renamed = artifacts.rename(db, edited, 'My chosen Page name')
    with patch('app.services.transcript_pages.render_chat_export', side_effect=AssertionError('Do not re-render an existing snapshot')):
        reused, exists = transcript_pages.save(db, 'owner', request('fresh-browser-request'), 'Renamed conversation')
    assert exists and reused == renamed
    assert reused['published_revision'] == first['latest_revision']
    assert len(reused['revisions']) == 2
    assert BeautifulSoup(reused['revisions'][0]['html'], 'html.parser').h1.text == 'Original conversation name'


def test_deleted_snapshot_gets_one_new_private_replacement_without_reviving_links(db):
    first, _ = transcript_pages.save(db, 'owner', request(), 'NIH award')
    first = artifacts.publish(db, first, first['latest_revision'])
    db.html_artifacts.update_one({'uuid': first['uuid']}, {'$set': {
        'deleted_at': datetime.now(timezone.utc), 'public_token': None,
        'published_revision': None, 'publications': [], 'revisions': [],
    }})
    second, reused = transcript_pages.save(db, 'owner', request('reopened'), 'NIH award')
    again, reused_again = transcript_pages.save(db, 'owner', request('reopened-again'), 'NIH award')
    assert not reused and reused_again
    assert second['uuid'] != first['uuid'] and again['uuid'] == second['uuid']
    assert not second['public_token'] and not second['team_id']
    assert db.html_artifacts.find_one({'uuid': first['uuid']})['deleted_at']


def test_concurrent_conversation_rename_reuses_the_winning_snapshot(db):
    create = artifacts.create
    def competing_save(database, user_id, title, html, request_id, source):
        create(database, user_id, 'Concurrent title', html, request_id, source)
        return create(database, user_id, title, html, request_id, source)
    with patch('app.services.transcript_pages.artifacts.create', side_effect=competing_save):
        saved, reused = transcript_pages.save(db, 'owner', request(), 'NIH award')
    assert reused and saved['title'] == 'Concurrent title'
    assert len(db.html_artifacts.docs) == 1


def test_title_fallbacks_are_readable_bounded_and_escaped(db):
    body = request()
    assert transcript_pages.page_title(body.messages, 'New chat', 'Chat transcript') == body.messages[0].content
    assert transcript_pages.page_title(body.messages, None, 'My report') == 'My report'
    assert len(transcript_pages.page_title(body.messages, 'x' * 300)) == 200
    saved, _ = transcript_pages.save(db, 'owner', body, 'NIH <img src=x onerror=alert(1)> & Award')
    soup = BeautifulSoup(artifacts.revision(saved)['html'], 'html.parser')
    assert not soup.select('img, script, [onerror]')
    assert soup.h1.text == 'NIH <img src=x onerror=alert(1)> & Award'


def test_content_limits_still_apply_before_reusing_a_snapshot(db):
    with pytest.raises(ValueError, match='too large'):
        transcript_pages.save(db, 'owner', request(messages=[{'role': 'assistant', 'content': 'x' * 300000, 'evidence': 'y' * 300000}]))
    assert db.html_artifacts.docs == []
