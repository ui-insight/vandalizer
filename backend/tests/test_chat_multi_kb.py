"""Chatting with several knowledge bases at once.

Chat carried exactly one KB: the request took a single ``knowledge_base_uuid``
and retrieval queried one collection. These cover the fan-out — each KB
retrieved at its own tuned settings, the pools merged so every attached KB is
represented, and each snippet labelled with the KB it came from.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services import chat_service
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _chunk(i: int, source: str) -> dict:
    return {
        "content": f"chunk {i} of {source}",
        "metadata": {"source_name": source, "source_id": f"src-{source}"},
        "chunk_id": f"{source}_chunk_{i}",
        "score": 0.1 * i,
        "similarity": round(0.95 - 0.05 * i, 2),
    }


class TestMultiKBSegment:
    @pytest.mark.asyncio
    async def test_merges_pools_and_labels_each_snippet_with_its_kb(self):
        pools = {
            "kb-a": [_chunk(0, "policy.pdf"), _chunk(1, "policy.pdf")],
            "kb-b": [_chunk(0, "award.pdf")],
        }

        async def fake_retrieve(kb_uuid, *_args, **_kwargs):
            return list(pools[kb_uuid])

        with (
            patch.object(chat_service, "_retrieve_kb_results", new=fake_retrieve),
            patch(
                "app.services.knowledge_service.resolve_openable_documents",
                new_callable=AsyncMock, return_value={},
            ),
        ):
            segment, sources = await chat_service._build_multi_kb_segment(
                [("kb-a", "Policies"), ("kb-b", "Awards")],
                "what is the closeout deadline?", "test-model",
            )

        assert segment is not None
        # Round-robin: the second KB is represented before the first KB's
        # second chunk, so a KB that ranks lower overall still reaches the model.
        assert [s["document_title"] for s in sources] == [
            "policy.pdf", "award.pdf", "policy.pdf",
        ]
        assert [s["kb_title"] for s in sources] == ["Policies", "Awards", "Policies"]
        assert [s["kb_uuid"] for s in sources] == ["kb-a", "kb-b", "kb-a"]
        # …and the prompt text says which KB each snippet came from.
        assert "policy.pdf — Policies" in segment.text
        assert "award.pdf — Awards" in segment.text

    @pytest.mark.asyncio
    async def test_caps_the_total_number_of_snippets(self):
        async def fake_retrieve(kb_uuid, *_args, **_kwargs):
            return [_chunk(i, f"{kb_uuid}.pdf") for i in range(8)]

        with (
            patch.object(chat_service, "_retrieve_kb_results", new=fake_retrieve),
            patch(
                "app.services.knowledge_service.resolve_openable_documents",
                new_callable=AsyncMock, return_value={},
            ),
        ):
            _segment, sources = await chat_service._build_multi_kb_segment(
                [("kb-a", "A"), ("kb-b", "B"), ("kb-c", "C")],
                "question?", "test-model",
            )

        assert len(sources) == chat_service.MULTI_KB_SNIPPET_BUDGET
        # The budget is shared evenly rather than spent on the first KB.
        assert {s["kb_uuid"] for s in sources} == {"kb-a", "kb-b", "kb-c"}

    @pytest.mark.asyncio
    async def test_one_failing_kb_does_not_lose_the_turn(self):
        async def fake_retrieve(kb_uuid, *_args, **_kwargs):
            if kb_uuid == "kb-broken":
                raise RuntimeError("chroma down")
            return [_chunk(0, "policy.pdf")]

        with (
            patch.object(chat_service, "_retrieve_kb_results", new=fake_retrieve),
            patch(
                "app.services.knowledge_service.resolve_openable_documents",
                new_callable=AsyncMock, return_value={},
            ),
        ):
            segment, sources = await chat_service._build_multi_kb_segment(
                [("kb-broken", "Broken"), ("kb-a", "Policies")],
                "question?", "test-model",
            )

        assert segment is not None
        assert [s["kb_title"] for s in sources] == ["Policies"]

    @pytest.mark.asyncio
    async def test_a_single_kb_is_not_labelled(self):
        """One KB reads as it always has — every existing chat sends one, and
        naming it would relabel all of them. The title is real here on purpose:
        an empty one would pass whatever the code did."""
        async def fake_retrieve(*_args, **_kwargs):
            return [_chunk(0, "policy.pdf")]

        with (
            patch.object(chat_service, "_retrieve_kb_results", new=fake_retrieve),
            patch(
                "app.services.knowledge_service.resolve_openable_documents",
                new_callable=AsyncMock, return_value={},
            ),
        ):
            segment, sources = await chat_service._build_multi_kb_segment(
                [("kb-a", "Export Control")], "question?", "test-model",
            )

        assert sources[0]["kb_title"] is None
        assert sources[0]["kb_uuid"] == "kb-a"
        assert "Export Control" not in segment.text


class TestManifestUnion:
    @pytest.mark.asyncio
    async def test_interleaves_so_a_big_kb_cannot_crowd_out_a_small_one(self):
        """The manifest block is cut by entry count and characters. Listing KB
        by KB let a large first KB fill it and leave the model told the last
        KB's documents don't exist here."""
        pools = [
            [{"source_uuid": f"a-{i}", "name": f"a{i}.pdf"} for i in range(50)],
            [{"source_uuid": "b-0", "name": "b0.pdf"}],
        ]
        merged = chat_service._round_robin_merge(pools, key="source_uuid")

        assert merged[1]["source_uuid"] == "b-0"


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
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


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as ac:
            yield ac


def _kb(uuid, title):
    kb = MagicMock()
    kb.uuid = uuid
    kb.title = title
    return kb


class TestChatRouteAcceptsSeveralKBs:
    @pytest.mark.asyncio
    async def test_rejects_more_than_the_cap(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.chat.access_control") as mock_ac,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())

            resp = await client.post(
                "/api/chat",
                json={
                    "message": "hi",
                    "knowledge_base_uuids": ["kb-1", "kb-2", "kb-3", "kb-4"],
                },
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 400
        assert "at most 3" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_every_attached_kb_is_authorized_and_passed_to_retrieval(self, client):
        user = _make_user()
        cookies, headers = _auth()
        kbs = {"kb-1": _kb("kb-1", "Policies"), "kb-2": _kb("kb-2", "Awards")}
        captured = {}

        async def fake_stream(**kwargs):
            captured.update(kwargs)
            yield '{"kind": "text", "content": "ok"}\n'

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.chat.access_control") as mock_ac,
            patch("app.routers.chat.organization_service") as mock_org,
            patch("app.routers.chat.activity_service") as mock_activity,
            patch("app.routers.chat.audit_service") as mock_audit,
            patch("app.routers.chat.ChatConversation") as MockConvo,
            patch("app.routers.chat.chat_stream", new=fake_stream),
            patch(
                "app.services.knowledge_service.record_kb_usage",
                new_callable=AsyncMock,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.get_authorized_knowledge_base = AsyncMock(
                side_effect=lambda uuid, *a, **kw: kbs.get(uuid),
            )
            convo = MagicMock()
            convo.uuid = "conv-1"
            convo.add_message = AsyncMock()
            convo.insert = AsyncMock()
            convo.save = AsyncMock()
            MockConvo.return_value = convo
            MockConvo.find_one = AsyncMock(return_value=None)
            activity = MagicMock()
            activity.id = "act-1"
            activity.title = "Chat"
            activity.save = AsyncMock()
            mock_activity.activity_start = AsyncMock(return_value=activity)
            mock_activity.get_activity = AsyncMock(return_value=None)
            mock_audit.log_event = AsyncMock()

            resp = await client.post(
                "/api/chat",
                json={"message": "hi", "knowledge_base_uuids": ["kb-1", "kb-2"]},
                cookies=cookies, headers=headers,
            )
            assert resp.status_code == 200
            await resp.aread()

        assert mock_ac.get_authorized_knowledge_base.await_count == 2
        assert captured["kbs"] == [("kb-1", "Policies"), ("kb-2", "Awards")]

    @pytest.mark.asyncio
    async def test_an_unauthorized_kb_in_the_list_is_a_404(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.chat.access_control") as mock_ac,
            patch("app.routers.chat.organization_service") as mock_org,
            patch(
                "app.services.knowledge_service.record_kb_usage",
                new_callable=AsyncMock,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.get_authorized_knowledge_base = AsyncMock(
                side_effect=[_kb("kb-1", "Policies"), None],
            )

            resp = await client.post(
                "/api/chat",
                json={"message": "hi", "knowledge_base_uuids": ["kb-1", "kb-secret"]},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404
