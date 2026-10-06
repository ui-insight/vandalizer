"""Reopening a conversation re-attaches what it was asked against.

Support ticket: reopening a conversation from the Activity rail brought back
the messages but not the documents (or knowledge bases) attached to it, so a
follow-up question went out with no document context and could not answer.
The selection lived only in the browser. The chat route now records it on the
conversation, and the history route hands it back — re-authorized, so an item
deleted or unshared since is counted but never named.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _item(uuid: str, title: str) -> MagicMock:
    item = MagicMock()
    item.uuid = uuid
    item.title = title
    return item


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as ac:
            yield ac


class TestChatRecordsTheSelection:
    @pytest.mark.asyncio
    async def test_documents_folders_and_kbs_are_recorded_on_the_conversation(self, client):
        """Folders are recorded as selected, not as the documents they expand
        into — reopening should show the folder chip, not 40 document chips."""
        user = _make_user()
        cookies, headers = _auth()
        docs = {"d-1": _item("d-1", "Proposal.pdf")}
        folders = {"f-1": _item("f-1", "Awards")}
        kbs = {"kb-1": _item("kb-1", "Policies")}

        async def fake_stream(**kwargs):
            yield '{"kind": "text", "content": "ok"}\n'

        in_folder = MagicMock()
        in_folder.find.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[_item("d-in-folder", "Award 1.pdf")],
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.chat.access_control") as mock_ac,
            patch("app.routers.chat.organization_service") as mock_org,
            patch("app.routers.chat.activity_service") as mock_activity,
            patch("app.routers.chat.ChatConversation") as MockConvo,
            patch("app.routers.chat.chat_stream", new=fake_stream),
            patch("app.models.document.SmartDocument", new=in_folder),
            patch(
                "app.services.knowledge_service.record_kb_usage",
                new_callable=AsyncMock,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.get_authorized_document = AsyncMock(
                side_effect=lambda uuid, *a, **kw: docs.get(uuid),
            )
            mock_ac.get_authorized_folder = AsyncMock(
                side_effect=lambda uuid, *a, **kw: folders.get(uuid),
            )
            mock_ac.get_authorized_knowledge_base = AsyncMock(
                side_effect=lambda uuid, *a, **kw: kbs.get(uuid),
            )
            mock_ac.can_view_document = MagicMock(return_value=True)
            convo = MagicMock()
            convo.uuid = "conv-1"
            convo.add_message = AsyncMock()
            convo.insert = AsyncMock()
            MockConvo.return_value = convo
            activity = MagicMock()
            activity.id = "act-1"
            activity.title = "Chat"
            activity.save = AsyncMock()
            mock_activity.activity_start = AsyncMock(return_value=activity)

            resp = await client.post(
                "/api/chat",
                json={
                    "message": "hi",
                    "document_uuids": ["d-1"],
                    "folder_uuids": ["f-1"],
                    "knowledge_base_uuids": ["kb-1"],
                },
                cookies=cookies, headers=headers,
            )
            assert resp.status_code == 200
            await resp.aread()

        assert convo.scope_document_uuids == ["d-1"]
        assert convo.scope_folder_uuids == ["f-1"]
        assert convo.scope_knowledge_base_uuids == ["kb-1"]
        convo.add_message.assert_awaited_once()


async def _history(client, conv, *, docs=None, folders=None, kbs=None):
    return (await _get_history(client, conv, docs=docs, folders=folders, kbs=kbs))["scope"]


async def _get_history(client, conv, *, docs=None, folders=None, kbs=None, activity=None):
    user = _make_user()
    cookies, headers = _auth()
    docs, folders, kbs = docs or {}, folders or {}, kbs or {}
    with (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.routers.chat.ChatConversation") as MockConv,
        patch("app.routers.chat.access_control") as mock_ac,
        patch("app.routers.chat.organization_service") as mock_org,
        patch("app.routers.chat.ActivityEvent") as MockActivity,
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        MockActivity.find_one = AsyncMock(return_value=activity)
        MockConv.find_one = AsyncMock(return_value=conv)
        mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
        mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
        mock_ac.get_authorized_document = AsyncMock(
            side_effect=lambda uuid, *a, **kw: docs.get(uuid),
        )
        mock_ac.get_authorized_folder = AsyncMock(
            side_effect=lambda uuid, *a, **kw: folders.get(uuid),
        )
        mock_ac.get_authorized_knowledge_base = AsyncMock(
            side_effect=lambda uuid, *a, **kw: kbs.get(uuid),
        )
        resp = await client.get(
            "/api/chat/history/conv-1", cookies=cookies, headers=headers,
        )
    assert resp.status_code == 200
    return resp.json()


def _conv(messages, *, doc_uuids=None, folder_uuids=None, kb_uuids=None):
    conv = MagicMock()
    conv.uuid = "conv-1"
    conv.user_id = "user1"
    conv.context_mode = "full"
    conv.context_cutoff_index = 0
    conv.scope_document_uuids = doc_uuids
    conv.scope_folder_uuids = folder_uuids
    conv.scope_knowledge_base_uuids = kb_uuids
    conv.get_messages = AsyncMock(return_value=messages)
    conv.get_url_attachments = AsyncMock(return_value=[])
    conv.get_file_attachments = AsyncMock(return_value=[])
    return conv


class TestHistoryRestoresTheSelection:
    @pytest.mark.asyncio
    async def test_the_recorded_selection_comes_back_with_titles(self, client):
        conv = _conv(
            [{"role": "user", "content": "q"}],
            doc_uuids=["d-1"], folder_uuids=["f-1"], kb_uuids=["kb-1"],
        )
        scope = await _history(
            client, conv,
            docs={"d-1": _item("d-1", "Proposal.pdf")},
            folders={"f-1": _item("f-1", "Awards")},
            kbs={"kb-1": _item("kb-1", "Policies")},
        )
        assert scope == {
            "documents": [{"uuid": "d-1", "title": "Proposal.pdf"}],
            "folders": [{"uuid": "f-1", "title": "Awards"}],
            "knowledge_bases": [{"uuid": "kb-1", "title": "Policies"}],
            "unavailable": 0,
        }

    @pytest.mark.asyncio
    async def test_items_no_longer_visible_are_counted_not_named(self, client):
        conv = _conv(
            [{"role": "user", "content": "q"}],
            doc_uuids=["d-1", "d-gone"], folder_uuids=[], kb_uuids=["kb-unshared"],
        )
        scope = await _history(
            client, conv, docs={"d-1": _item("d-1", "Proposal.pdf")},
        )
        assert scope["documents"] == [{"uuid": "d-1", "title": "Proposal.pdf"}]
        assert scope["knowledge_bases"] == []
        assert scope["unavailable"] == 2
        assert "d-gone" not in str(scope) and "kb-unshared" not in str(scope)

    @pytest.mark.asyncio
    async def test_an_empty_recorded_selection_is_empty_not_unknown(self, client):
        """A chat asked with nothing attached reopens with nothing attached —
        the client clears its selection rather than keeping a stale one."""
        conv = _conv(
            [{"role": "user", "content": "q"}],
            doc_uuids=[], folder_uuids=[], kb_uuids=[],
        )
        scope = await _history(client, conv)
        assert scope == {
            "documents": [], "folders": [], "knowledge_bases": [], "unavailable": 0,
        }

    @pytest.mark.asyncio
    async def test_an_older_conversation_falls_back_to_its_last_questions_documents(self, client):
        """Conversations saved before the selection was recorded still carry
        the documents each question was asked against; KBs are unknown, so
        they stay None and the client leaves its KB chips alone."""
        conv = _conv([
            {"role": "user", "content": "first", "source_documents": [
                {"uuid": "d-old", "title": "Old.pdf"},
            ]},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "second", "source_documents": [
                {"uuid": "d-1", "title": "Proposal.pdf"},
                {"truncated": 4},
            ]},
            {"role": "assistant", "content": "b"},
        ])
        scope = await _history(
            client, conv,
            docs={
                "d-old": _item("d-old", "Old.pdf"),
                "d-1": _item("d-1", "Proposal.pdf"),
            },
        )
        assert scope["documents"] == [{"uuid": "d-1", "title": "Proposal.pdf"}]
        assert scope["folders"] is None
        assert scope["knowledge_bases"] is None

    @pytest.mark.asyncio
    async def test_an_older_conversation_with_nothing_recorded_is_unknown(self, client):
        conv = _conv([{"role": "user", "content": "q"}])
        scope = await _history(client, conv)
        assert scope == {
            "documents": None, "folders": None, "knowledge_bases": None,
            "unavailable": 0,
        }


class TestHistoryNamesTheActivityToContinue:
    @pytest.mark.asyncio
    async def test_a_follow_up_continues_the_reopened_conversation(self, client):
        """The client continues a conversation by its activity id. Reopening
        loaded the messages but not the activity, so the next question
        started a new conversation without the earlier turns."""
        activity = MagicMock()
        activity.id = "act-1"
        data = await _get_history(
            client, _conv([{"role": "user", "content": "q"}]), activity=activity,
        )
        assert data["activity_id"] == "act-1"

    @pytest.mark.asyncio
    async def test_no_activity_is_none(self, client):
        data = await _get_history(client, _conv([{"role": "user", "content": "q"}]))
        assert data["activity_id"] is None
