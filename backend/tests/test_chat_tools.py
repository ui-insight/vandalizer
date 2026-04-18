"""Tests for app.services.chat_tools — agentic chat tool functions.

Tests verify authorization logic, result structure, and edge cases
using mocked dependencies and database queries.
"""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_deps(**overrides):
    """Build a minimal AgenticChatDeps-like object for testing."""

    @dataclass
    class FakeDeps:
        user: MagicMock = field(default_factory=lambda: MagicMock(user_id="user1"))
        user_id: str = "user1"
        team_id: str | None = "team1"
        team_access: MagicMock = field(default_factory=MagicMock)
        organization_id: str | None = None
        system_config_doc: dict = field(default_factory=dict)
        model_name: str = "gpt-4o-mini"
        context_document_uuids: list = field(default_factory=list)
        active_kb_uuid: str | None = None
        quality_annotations: dict = field(default_factory=dict)

    deps = FakeDeps(**{k: v for k, v in overrides.items() if k in FakeDeps.__dataclass_fields__})
    return deps


def _make_context(**overrides):
    """Build a fake RunContext wrapping deps."""
    ctx = MagicMock()
    ctx.deps = _make_deps(**overrides)
    return ctx


def _make_doc(**kwargs):
    """Build a fake SmartDocument."""
    doc = MagicMock()
    doc.uuid = kwargs.get("uuid", "doc-1")
    doc.title = kwargs.get("title", "Test Doc")
    doc.extension = kwargs.get("extension", ".pdf")
    doc.num_pages = kwargs.get("num_pages", 5)
    doc.classification = kwargs.get("classification", "unrestricted")
    doc.folder = kwargs.get("folder", None)
    doc.team_id = kwargs.get("team_id", "team1")
    doc.user_id = kwargs.get("user_id", "user1")
    doc.raw_text = kwargs.get("raw_text", "Sample document text.")
    doc.soft_deleted = kwargs.get("soft_deleted", False)
    doc.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
    return doc


# ---------------------------------------------------------------------------
# search_documents
# ---------------------------------------------------------------------------


class TestWordsToRegex:
    def test_single_word(self):
        from app.services.chat_tools import _words_to_regex

        assert _words_to_regex("composer") == "composer"

    def test_multi_word(self):
        from app.services.chat_tools import _words_to_regex
        import re

        pattern = _words_to_regex("composer agreement")
        # Should match a title where both words appear (any order, any separator)
        assert re.search(pattern, "Composer-Performer_Agreement_copy_4.pdf", re.IGNORECASE)
        assert re.search(pattern, "Agreement for Composer", re.IGNORECASE)
        # Should NOT match if one word is missing
        assert not re.search(pattern, "Composer-Performer_copy_4.pdf", re.IGNORECASE)

    def test_multi_word_across_newlines(self):
        from app.services.chat_tools import _words_to_regex
        import re

        pattern = _words_to_regex("composer performance agreement")
        raw_text = (
            "Composer-Performer Agreement\n"
            "Performance Date & Time: 4.29.26 at 7:30pm\n"
            "Performance Venue: Haddock"
        )
        assert re.search(pattern, raw_text, re.IGNORECASE)

    def test_empty_query(self):
        from app.services.chat_tools import _words_to_regex

        assert _words_to_regex("") == ""

    def test_special_characters_escaped(self):
        from app.services.chat_tools import _words_to_regex
        import re

        # Use a quoted phrase so punctuation survives tokenization
        pattern = _words_to_regex('"a.b" copy')
        assert re.search(pattern, "a.b copy_2", re.IGNORECASE)
        # The dot should be escaped, not match any character
        assert not re.search(pattern, "axb copy_2", re.IGNORECASE)


class TestSearchDocuments:
    @pytest.mark.asyncio
    async def test_returns_matching_docs(self):
        from app.services.chat_tools import search_documents

        doc = _make_doc()
        ctx = _make_context()

        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            mock_query = AsyncMock(return_value=[doc])
            MockDoc.find.return_value.sort.return_value.limit.return_value.to_list = mock_query

            result = await search_documents(ctx, "Test")

        assert len(result) == 1
        assert result[0]["uuid"] == "doc-1"
        assert result[0]["title"] == "Test Doc"

    @pytest.mark.asyncio
    async def test_default_query_searches_title_only(self):
        """Default (search_content=False) should match title only — raw_text
        scans on a non-indexed field are expensive and will time out on
        large workspaces."""
        from app.services.chat_tools import search_documents

        ctx = _make_context()
        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
            await search_documents(ctx, "composer agreement")

        call_args = MockDoc.find.call_args[0][0]
        assert "$and" in call_args
        text_filter = call_args["$and"][2]
        assert "title" in text_filter
        assert "$or" not in text_filter

    @pytest.mark.asyncio
    async def test_search_content_expands_to_raw_text(self):
        """search_content=True opts in to the full-scan $or across title
        and raw_text."""
        from app.services.chat_tools import search_documents

        ctx = _make_context()
        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
            await search_documents(ctx, "composer agreement", search_content=True)

        call_args = MockDoc.find.call_args[0][0]
        text_filter = call_args["$and"][2]
        assert "$or" in text_filter
        fields = {list(c.keys())[0] for c in text_filter["$or"]}
        assert fields == {"title", "raw_text"}

    @pytest.mark.asyncio
    async def test_empty_query_returns_results(self):
        from app.services.chat_tools import search_documents

        ctx = _make_context()
        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
            result = await search_documents(ctx, "")

        assert result == []


# ---------------------------------------------------------------------------
# list_knowledge_bases
# ---------------------------------------------------------------------------


class TestListKnowledgeBases:
    @pytest.mark.asyncio
    async def test_returns_accessible_kbs(self):
        from app.services.chat_tools import list_knowledge_bases

        kb = MagicMock()
        kb.uuid = "kb-1"
        kb.title = "My KB"
        kb.description = "Test"
        kb.status = "ready"
        kb.total_sources = 3
        kb.total_chunks = 100
        kb.verified = False
        kb.shared_with_team = True

        ctx = _make_context()
        with patch("app.services.chat_tools.KnowledgeBase") as MockKB:
            MockKB.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[kb])
            result = await list_knowledge_bases(ctx)

        assert len(result) == 1
        assert result[0]["uuid"] == "kb-1"
        assert result[0]["total_chunks"] == 100


# ---------------------------------------------------------------------------
# get_document_text
# ---------------------------------------------------------------------------


class TestGetDocumentText:
    @pytest.mark.asyncio
    async def test_returns_text(self):
        from app.services.chat_tools import get_document_text

        doc = _make_doc(raw_text="Hello world content")
        ctx = _make_context()

        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            result = await get_document_text(ctx, "doc-1")

        assert result["title"] == "Test Doc"
        assert "Hello world" in result["text"]
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_not_found(self):
        from app.services.chat_tools import get_document_text

        ctx = _make_context()
        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=None)
            result = await get_document_text(ctx, "nonexistent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_unauthorized_different_team(self):
        from app.services.chat_tools import get_document_text

        doc = _make_doc(team_id="other-team", user_id="other-user")
        ctx = _make_context(team_id="team1", user_id="user1")

        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            result = await get_document_text(ctx, "doc-1")

        assert "error" in result
        assert "access" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_truncation(self):
        from app.services.chat_tools import get_document_text

        doc = _make_doc(raw_text="x" * 50000)
        ctx = _make_context()

        with patch("app.services.chat_tools.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            result = await get_document_text(ctx, "doc-1")

        assert result["truncated"] is True
        assert result["total_chars"] == 50000
        assert len(result["text"]) == 30000


# ---------------------------------------------------------------------------
# get_quality_info
# ---------------------------------------------------------------------------


class TestGetQualityInfo:
    @pytest.mark.asyncio
    async def test_returns_validation_data(self):
        from app.services.chat_tools import get_quality_info

        run = MagicMock()
        run.score = 87.5
        run.accuracy = 0.9
        run.consistency = 0.85
        run.grade = "B"
        run.num_test_cases = 5
        run.num_runs = 3
        run.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01"))
        run.score_breakdown = {"raw_score": 87.5}

        ctx = _make_context()
        with patch("app.services.chat_tools.ValidationRun") as MockVR, \
             patch("app.services.chat_tools.QualityAlert") as MockQA:
            MockVR.find.return_value.sort.return_value.first_or_none = AsyncMock(return_value=run)
            MockQA.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
            result = await get_quality_info(ctx, "search_set", "ss-1")

        assert result["score"] == 87.5
        assert result["accuracy"] == 0.9
        assert result["active_alerts"] == []

    @pytest.mark.asyncio
    async def test_no_validation_runs(self):
        from app.services.chat_tools import get_quality_info

        ctx = _make_context()
        with patch("app.services.chat_tools.ValidationRun") as MockVR, \
             patch("app.services.chat_tools.QualityAlert") as MockQA:
            MockVR.find.return_value.sort.return_value.first_or_none = AsyncMock(return_value=None)
            MockQA.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
            result = await get_quality_info(ctx, "search_set", "ss-1")

        assert result["score"] is None
        assert "No validation runs" in result["note"]


# ---------------------------------------------------------------------------
# run_extraction
# ---------------------------------------------------------------------------


class TestRunExtraction:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from app.services.chat_tools import run_extraction

        ctx = _make_context()
        with patch("app.services.chat_tools.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)
            result = await run_extraction(ctx, "nonexistent", ["doc-1"])

        assert "error" in result

    @pytest.mark.asyncio
    async def test_unauthorized(self):
        from app.services.chat_tools import run_extraction

        ss = MagicMock()
        ss.uuid = "ss-1"
        ss.verified = False
        ss.user_id = "other-user"
        ss.team_id = "other-team"

        ctx = _make_context(team_id="team1", user_id="user1")
        with patch("app.services.chat_tools.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)
            result = await run_extraction(ctx, "ss-1", ["doc-1"])

        assert "error" in result
        assert "access" in result["error"].lower()


# ---------------------------------------------------------------------------
# create_knowledge_base
# ---------------------------------------------------------------------------


class TestCreateKnowledgeBase:
    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import create_knowledge_base

        ctx = _make_context()
        result = await create_knowledge_base(ctx, "My New KB", "Desc", confirmed=False)

        assert result["needs_confirmation"] is True
        assert "My New KB" in result["preview"]

    @pytest.mark.asyncio
    async def test_creates_kb_when_confirmed(self):
        from app.services.chat_tools import create_knowledge_base

        fake_kb = MagicMock()
        fake_kb.uuid = "new-kb"
        fake_kb.title = "My New KB"
        fake_kb.description = "Desc"
        fake_kb.status = "empty"

        ctx = _make_context()
        with patch("app.services.knowledge_service.create_knowledge_base", new_callable=AsyncMock, return_value=fake_kb):
            result = await create_knowledge_base(ctx, "My New KB", "Desc", confirmed=True)

        assert result["uuid"] == "new-kb"
        assert "created" in result["message"].lower()


# ---------------------------------------------------------------------------
# run_workflow
# ---------------------------------------------------------------------------


class TestRunWorkflow:
    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import run_workflow

        ctx = _make_context()
        wf = MagicMock()
        wf.name = "My Workflow"
        with patch("app.services.chat_tools.Workflow") as MockWF:
            MockWF.get = AsyncMock(return_value=wf)
            result = await run_workflow(ctx, "wf-1", ["doc-1"], confirmed=False)

        assert result["needs_confirmation"] is True
        assert "My Workflow" in result["preview"]

    @pytest.mark.asyncio
    async def test_returns_session_id_when_confirmed(self):
        from app.services.chat_tools import run_workflow

        ctx = _make_context()
        wf = MagicMock()
        wf.name = "My Workflow"
        wf.verified = False
        wf.user_id = "user1"
        wf.team_id = "team1"
        with patch("app.services.chat_tools.Workflow") as MockWF, \
             patch("app.services.workflow_service.run_workflow", new_callable=AsyncMock, return_value="session-123"):
            MockWF.get = AsyncMock(return_value=wf)
            result = await run_workflow(ctx, "wf-1", ["doc-1"], confirmed=True)

        assert result["session_id"] == "session-123"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_handles_error_when_confirmed(self):
        from app.services.chat_tools import run_workflow

        ctx = _make_context()
        wf = MagicMock()
        wf.name = "Error Workflow"
        wf.verified = False
        wf.user_id = "user1"
        wf.team_id = "team1"
        with patch("app.services.chat_tools.Workflow") as MockWF, \
             patch("app.services.workflow_service.run_workflow", new_callable=AsyncMock, side_effect=ValueError("Workflow not found")):
            MockWF.get = AsyncMock(return_value=wf)
            result = await run_workflow(ctx, "nonexistent", ["doc-1"], confirmed=True)

        assert "error" in result
        assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# get_workflow_status
# ---------------------------------------------------------------------------


class TestGetWorkflowStatus:
    @pytest.mark.asyncio
    async def test_completed_workflow(self):
        from app.services.chat_tools import get_workflow_status

        status_data = {
            "status": "completed",
            "num_steps_completed": 3,
            "num_steps_total": 3,
            "current_step_name": None,
            "current_step_detail": None,
            "current_step_preview": None,
            "final_output": {"output": "Final result text"},
            "steps_output": {},
            "approval_request_id": None,
        }

        ctx = _make_context()
        with patch("app.services.workflow_service.get_workflow_status", new_callable=AsyncMock, return_value=status_data):
            result = await get_workflow_status(ctx, "session-123")

        assert result["status"] == "completed"
        assert result["output"] == "Final result text"

    @pytest.mark.asyncio
    async def test_not_found(self):
        from app.services.chat_tools import get_workflow_status

        ctx = _make_context()
        with patch("app.services.workflow_service.get_workflow_status", new_callable=AsyncMock, return_value=None):
            result = await get_workflow_status(ctx, "nonexistent")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_paused_workflow(self):
        from app.services.chat_tools import get_workflow_status

        status_data = {
            "status": "paused",
            "num_steps_completed": 1,
            "num_steps_total": 3,
            "current_step_name": "Approval",
            "current_step_detail": None,
            "current_step_preview": None,
            "final_output": None,
            "steps_output": {},
            "approval_request_id": "apr-1",
        }

        ctx = _make_context()
        with patch("app.services.workflow_service.get_workflow_status", new_callable=AsyncMock, return_value=status_data):
            result = await get_workflow_status(ctx, "session-123")

        assert result["status"] == "paused"
        assert result["approval_request_id"] == "apr-1"
        assert "approval" in result["message"].lower()
