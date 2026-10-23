"""Activity-panel ticket: a run records the chat that started it and the
documents it read, so the list can nest it under that chat and tell two runs
of the same template apart."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.activity import ActivityEvent


def _doc(uuid, title):
    return MagicMock(uuid=uuid, title=title)


def _find_returning(docs):
    query = MagicMock()
    query.to_list = AsyncMock(return_value=docs)
    return MagicMock(return_value=query)


class TestDocumentTitlesFor:
    @pytest.mark.asyncio
    async def test_keeps_the_given_order_and_skips_missing_documents(self):
        from app.services.activity_service import document_titles_for

        docs = [_doc("b", "NIFA.pdf"), _doc("a", "subaward-agreement.pdf")]
        with patch("app.models.document.SmartDocument.find", _find_returning(docs)):
            titles = await document_titles_for(["a", "gone", "b", "a"])
        assert titles == ["subaward-agreement.pdf", "NIFA.pdf"]

    @pytest.mark.asyncio
    async def test_no_documents_makes_no_query(self):
        from app.services.activity_service import document_titles_for

        find = _find_returning([])
        with patch("app.models.document.SmartDocument.find", find):
            assert await document_titles_for(None) == []
        find.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_lookup_failure_never_fails_the_run(self):
        from app.services.activity_service import document_titles_for

        with patch("app.models.document.SmartDocument.find", side_effect=RuntimeError("db down")):
            assert await document_titles_for(["a"]) == []


class TestActivityStart:
    @pytest.mark.asyncio
    async def test_records_the_source_chat_and_document_titles(self):
        from app.models.activity import ActivityType
        from app.services import activity_service

        model = MagicMock()
        model.return_value.insert = AsyncMock()
        with patch.object(activity_service, "document_titles_for",
                          AsyncMock(return_value=["subaward-agreement.pdf"])), \
             patch.object(activity_service, "ActivityEvent", model):
            await activity_service.activity_start(
                type=ActivityType.SEARCH_SET_RUN, user_id="u1", title="NSF Subaward Extraction",
                document_uuids=["doc-1"], source_conversation_id="conv-1",
            )
        kwargs = model.call_args.kwargs
        assert kwargs["source_conversation_id"] == "conv-1"
        assert kwargs["document_titles"] == ["subaward-agreement.pdf"]
        # The chat's own entry field stays empty: deleting a run must never
        # cascade into deleting the chat that ran it.
        assert kwargs["conversation_id"] is None

    def test_to_dict_carries_the_new_fields(self):
        ev = ActivityEvent.model_construct(
            type="workflow_run", status="completed", title="Subaward Review Summary v2",
            user_id="u1", source_conversation_id="conv-1", document_titles=["NIFA.pdf"],
            tags=["chat"], started_at=None, finished_at=None, last_updated_at=None,
            workflow=None, meta_summary={}, result_snapshot={},
        )
        d = ev.to_dict()
        assert d["source_conversation_id"] == "conv-1"
        assert d["document_titles"] == ["NIFA.pdf"]
        assert d["tags"] == ["chat"]


class TestChatStartedWorkflowRun:
    @pytest.mark.asyncio
    async def test_records_the_chat_and_the_workflow_name(self):
        from types import SimpleNamespace

        from app.services import chat_tools

        model = MagicMock()
        model.return_value.insert = AsyncMock()
        model.return_value.id = "507f1f77bcf86cd799439011"
        ctx = MagicMock()
        ctx.deps.team_id = "team1"
        ctx.deps.user_id = "u1"
        ctx.deps.conversation = SimpleNamespace(uuid="conv-1")
        wf = MagicMock(id="wf-1")
        wf.name = "Subaward Review Summary v2"
        with patch("app.models.activity.ActivityEvent", model), \
             patch("app.services.activity_service.document_titles_for",
                   AsyncMock(return_value=["NIFA.pdf"])), \
             patch.object(chat_tools, "_workflow_run_model", return_value=("m", None)), \
             patch("app.services.workflow_service.run_workflow", AsyncMock(return_value="s-1")):
            await chat_tools._execute_workflow(ctx, wf, ["doc-1"])

        kwargs = model.call_args.kwargs
        assert kwargs["source_conversation_id"] == "conv-1"
        assert kwargs["document_titles"] == ["NIFA.pdf"]
        assert kwargs["title"] == "Subaward Review Summary v2"
        assert kwargs["tags"] == ["chat"]
