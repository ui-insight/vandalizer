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


class _AlwaysEqual:
    """Compares equal to any value — so the pre-approved confirmation entry
    matches whatever action fingerprint a write tool computes."""

    def __eq__(self, other):
        return True

    def __hash__(self):
        return 0


class _ArmedAny(dict):
    """A pending-confirmation entry that matches any action and reads as if it
    were armed on an earlier turn (``turn`` = -1)."""

    def get(self, key, default=None):
        if key == "fp":
            return _AlwaysEqual()
        if key == "turn":
            return -1
        return default


class _PreApprovedConversation:
    """Test seam for chat_tools._confirm_gate.

    These tests exercise tool *behavior*, not the confirmation handshake, so the
    conversation always presents one pre-approved entry: a single
    ``confirmed=True`` call executes (as if the user had approved on a prior
    turn), while a ``confirmed=False`` call still returns the preview. The gate's
    actual same-turn / cross-turn enforcement is covered in
    test_chat_security_hardening.py.
    """

    messages: list = []

    @property
    def pending_confirmations(self):
        return [_ArmedAny()]

    @pending_confirmations.setter
    def pending_confirmations(self, value):
        pass  # always pre-approved; ignore arm/clear writes

    async def save(self):
        pass


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
        active_project_uuid: str | None = None
        quality_annotations: dict = field(default_factory=dict)
        citation_annotations: dict = field(default_factory=dict)
        conversation: object = field(default_factory=_PreApprovedConversation)
        turn_marker: int = 5

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

    @pytest.mark.asyncio
    async def test_text_input_creates_temp_doc_and_runs(self):
        from app.services.chat_tools import run_workflow

        ctx = _make_context()
        wf = MagicMock()
        wf.name = "Bed Flow"
        wf.verified = False
        wf.user_id = "user1"
        wf.team_id = "team1"
        wf.input_config = {"trigger_type": "text_input"}
        with patch("app.services.chat_tools.Workflow") as MockWF, \
             patch("app.services.workflow_service.create_temp_documents_from_text", new_callable=AsyncMock, return_value=["TMP1"]) as mock_temp, \
             patch("app.services.workflow_service.run_workflow", new_callable=AsyncMock, return_value="session-ti") as mock_run:
            MockWF.get = AsyncMock(return_value=wf)
            result = await run_workflow(ctx, "wf-1", text_input="Bed 2", confirmed=True)

        assert result["session_id"] == "session-ti"
        # Typed text became a temp document fed into the run.
        mock_temp.assert_awaited_once()
        assert "TMP1" in mock_run.await_args.kwargs["document_uuids"]

    @pytest.mark.asyncio
    async def test_text_input_required_when_missing(self):
        from app.services.chat_tools import run_workflow

        ctx = _make_context()
        wf = MagicMock()
        wf.name = "Bed Flow"
        wf.verified = False
        wf.user_id = "user1"
        wf.team_id = "team1"
        wf.input_config = {"trigger_type": "text_input"}
        with patch("app.services.chat_tools.Workflow") as MockWF:
            MockWF.get = AsyncMock(return_value=wf)
            result = await run_workflow(ctx, "wf-1", confirmed=False)

        assert "error" in result
        assert "text input" in result["error"].lower()


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


# ---------------------------------------------------------------------------
# list_folders
# ---------------------------------------------------------------------------


class TestListFolders:
    @pytest.mark.asyncio
    async def test_returns_accessible_folders(self):
        from app.services.chat_tools import list_folders

        folder = MagicMock(uuid="f1", title="Grants", parent_id="0", team_id=None)
        ctx = _make_context()
        with patch("app.services.chat_tools.SmartFolder") as MockFolder:
            MockFolder.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
                return_value=[folder]
            )
            result = await list_folders(ctx)

        assert len(result) == 1
        assert result[0]["uuid"] == "f1"
        assert result[0]["title"] == "Grants"
        assert result[0]["parent_id"] == "0"


# ---------------------------------------------------------------------------
# save_to_folder
# ---------------------------------------------------------------------------


class TestSaveToFolder:
    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        result = await save_to_folder(ctx, "My Memo", "Some content", confirmed=False)

        assert result["needs_confirmation"] is True
        assert result["action"] == "save_to_folder"
        assert "My Memo.md" in result["preview"]
        # Root save defaults to the personal root folder
        assert result["destination_folder"] == "0"

    @pytest.mark.asyncio
    async def test_rejects_unsupported_extension(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        result = await save_to_folder(ctx, "t", "c", extension="exe", confirmed=True)
        assert "Unsupported" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_empty_content(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        result = await save_to_folder(ctx, "Title", "   ", confirmed=True)
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_empty_title(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        result = await save_to_folder(ctx, "   ", "content", confirmed=True)
        assert "title" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_saves_to_root_when_confirmed(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        mock_doc = MagicMock()
        mock_doc.insert = AsyncMock()
        mock_storage = MagicMock()
        mock_storage.write = AsyncMock()

        with patch("app.services.chat_tools.SmartDocument", return_value=mock_doc), \
             patch("app.services.storage.get_storage", return_value=mock_storage), \
             patch("app.celery_app.celery_app") as MockCelery:
            result = await save_to_folder(
                ctx, "My Memo", "# Heading\n\nBody text.", confirmed=True
            )

        assert result["title"] == "My Memo.md"
        assert result["folder"] == "0"
        assert result["extension"] == "md"
        assert "document_uuid" in result
        mock_storage.write.assert_awaited_once()
        mock_doc.insert.assert_awaited_once()
        # Saved doc is dispatched for semantic ingestion so it's chat-searchable
        MockCelery.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_unauthorized_folder_blocks_save(self):
        from app.services.chat_tools import save_to_folder

        ctx = _make_context()
        with patch(
            "app.services.access_control.get_authorized_folder",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await save_to_folder(
                ctx, "Memo", "content", folder_uuid="nope", confirmed=True
            )
        assert "access" in result["error"].lower() or "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# Phase 8 — Project tools
# ---------------------------------------------------------------------------


def _fake_project(**kw):
    p = MagicMock()
    p.uuid = kw.get("uuid", "p1")
    p.title = kw.get("title", "NIH R01")
    p.state = kw.get("state", "active")
    return p


class TestListProjectDocuments:
    @pytest.mark.asyncio
    async def test_no_active_project(self):
        from app.services.chat_tools import list_project_documents

        ctx = _make_context()  # active_project_uuid is None
        result = await list_project_documents(ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_happy_path(self):
        from app.services.chat_tools import list_project_documents

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.get_project_document_uuids",
                  new_callable=AsyncMock, return_value=["doc-1", "doc-2"]),
            patch("app.services.chat_tools.SmartDocument") as MockDoc,
        ):
            MockDoc.find_one = AsyncMock(side_effect=[_make_doc(uuid="doc-1"),
                                                      _make_doc(uuid="doc-2")])
            result = await list_project_documents(ctx)

        assert result["document_count"] == 2
        assert len(result["documents"]) == 2


class TestRunPinOnProject:
    @pytest.mark.asyncio
    async def test_no_active_project(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context()
        result = await run_pin_on_project(ctx, "workflow", "wf-1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_automation_unsupported(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        with patch("app.services.project_service.get_authorized_project",
                   new_callable=AsyncMock, return_value=_fake_project()):
            result = await run_pin_on_project(ctx, "automation", "a-1")
        assert "error" in result
        assert "runnable" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_not_manager(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=False),
        ):
            result = await run_pin_on_project(ctx, "workflow", "wf-1")
        assert "error" in result
        assert "edit access" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_pin_not_found(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.list_pins",
                  new_callable=AsyncMock, return_value=[]),
        ):
            result = await run_pin_on_project(ctx, "workflow", "wf-1")
        assert "error" in result
        assert "not pinned" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_preview_when_unconfirmed(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        pins = [{"pin_type": "workflow", "target_id": "wf-1", "name": "Compliance"}]
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.list_pins",
                  new_callable=AsyncMock, return_value=pins),
            patch("app.services.project_service.get_project_document_uuids",
                  new_callable=AsyncMock, return_value=["d1", "d2"]),
        ):
            result = await run_pin_on_project(ctx, "workflow", "wf-1")
        assert result["needs_confirmation"] is True
        assert result["document_count"] == 2
        assert "Compliance" in result["preview"]

    @pytest.mark.asyncio
    async def test_empty_documents(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        pins = [{"pin_type": "extraction", "target_id": "ss-1", "name": "Budget"}]
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.list_pins",
                  new_callable=AsyncMock, return_value=pins),
            patch("app.services.project_service.get_project_document_uuids",
                  new_callable=AsyncMock, return_value=[]),
        ):
            result = await run_pin_on_project(ctx, "extraction", "ss-1")
        assert "error" in result
        assert "no documents" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_extraction_execute(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        pins = [{"pin_type": "extraction", "target_id": "ss-1", "name": "Budget"}]
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.list_pins",
                  new_callable=AsyncMock, return_value=pins),
            patch("app.services.project_service.get_project_document_uuids",
                  new_callable=AsyncMock, return_value=["d1"]),
            patch("app.services.chat_tools.SearchSet") as MockSS,
            patch("app.services.chat_tools._execute_extraction",
                  new_callable=AsyncMock, return_value={"entity_count": 3}) as mock_exec,
        ):
            MockSS.find_one = AsyncMock(return_value=MagicMock(uuid="ss-1"))
            result = await run_pin_on_project(ctx, "extraction", "ss-1", confirmed=True)

        mock_exec.assert_awaited_once()
        assert result["entity_count"] == 3
        assert result["project"] == "NIH R01"

    @pytest.mark.asyncio
    async def test_workflow_execute_with_truncation_note(self):
        from app.services.chat_tools import run_pin_on_project

        ctx = _make_context(active_project_uuid="p1")
        pins = [{"pin_type": "workflow", "target_id": "wf-1", "name": "Compliance"}]
        many = [f"d{i}" for i in range(12)]
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.list_pins",
                  new_callable=AsyncMock, return_value=pins),
            patch("app.services.project_service.get_project_document_uuids",
                  new_callable=AsyncMock, return_value=many),
            patch("app.services.chat_tools.Workflow") as MockWf,
            patch("app.services.chat_tools._execute_workflow",
                  new_callable=AsyncMock, return_value={"session_id": "s1"}),
        ):
            MockWf.get = AsyncMock(return_value=MagicMock(id="wf-1"))
            result = await run_pin_on_project(ctx, "workflow", "wf-1", confirmed=True)

        assert result["session_id"] == "s1"
        assert "first 10" in result["note"].lower()


class TestProjectManageTools:
    @pytest.mark.asyncio
    async def test_pin_invalid_type(self):
        from app.services.chat_tools import pin_to_project

        ctx = _make_context(active_project_uuid="p1")
        with patch("app.services.project_service.get_authorized_project",
                   new_callable=AsyncMock, return_value=_fake_project()):
            result = await pin_to_project(ctx, "banana", "x")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_pin_not_manager(self):
        from app.services.chat_tools import pin_to_project

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=False),
        ):
            result = await pin_to_project(ctx, "workflow", "wf-1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_pin_preview_then_execute(self):
        from app.services.chat_tools import pin_to_project

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.add_pin",
                  new_callable=AsyncMock) as mock_add,
        ):
            preview = await pin_to_project(ctx, "workflow", "wf-1")
            assert preview["needs_confirmation"] is True
            done = await pin_to_project(ctx, "workflow", "wf-1", confirmed=True)

        mock_add.assert_awaited_once()
        assert done["ok"] is True

    @pytest.mark.asyncio
    async def test_unpin_execute(self):
        from app.services.chat_tools import unpin_from_project

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.remove_pin",
                  new_callable=AsyncMock) as mock_rm,
        ):
            done = await unpin_from_project(ctx, "workflow", "wf-1", confirmed=True)

        mock_rm.assert_awaited_once()
        assert done["ok"] is True

    @pytest.mark.asyncio
    async def test_set_status_invalid(self):
        from app.services.chat_tools import set_project_status

        ctx = _make_context(active_project_uuid="p1")
        with patch("app.services.project_service.get_authorized_project",
                   new_callable=AsyncMock, return_value=_fake_project()):
            result = await set_project_status(ctx, "bogus")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_set_status_not_manager(self):
        from app.services.chat_tools import set_project_status

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=False),
        ):
            result = await set_project_status(ctx, "submitted")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_set_status_execute(self):
        from app.services.chat_tools import set_project_status

        ctx = _make_context(active_project_uuid="p1")
        with (
            patch("app.services.project_service.get_authorized_project",
                  new_callable=AsyncMock, return_value=_fake_project()),
            patch("app.services.project_service.can_manage_project",
                  new_callable=AsyncMock, return_value=True),
            patch("app.services.project_service.update_project",
                  new_callable=AsyncMock) as mock_upd,
        ):
            preview = await set_project_status(ctx, "submitted")
            assert preview["needs_confirmation"] is True
            done = await set_project_status(ctx, "submitted", confirmed=True)

        mock_upd.assert_awaited_once()
        assert done["state"] == "submitted"


class TestCreateExtractionAutoPin:
    def _patches(self, ss, project, can_manage):
        """Common patch set for the create_extraction_from_document flow."""
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch("app.services.chat_tools.SmartDocument"))
        # Document auth + text
        doc = _make_doc(uuid="d1", team_id="team1", user_id="user1")
        from app.services import chat_tools
        chat_tools.SmartDocument.find_one = AsyncMock(return_value=doc)
        stack.enter_context(patch("app.services.search_set_service.create_search_set",
                                  new_callable=AsyncMock, return_value=ss))
        stack.enter_context(patch("app.services.search_set_service.build_from_documents",
                                  new_callable=AsyncMock, return_value=(["PI name"], "Smart Title")))
        stack.enter_context(patch("app.services.library_service.get_or_create_personal_library",
                                  new_callable=AsyncMock, return_value=MagicMock(id="lib")))
        stack.enter_context(patch("app.services.library_service.add_item",
                                  new_callable=AsyncMock))
        stack.enter_context(patch("app.services.project_service.get_authorized_project",
                                  new_callable=AsyncMock, return_value=project))
        stack.enter_context(patch("app.services.project_service.can_manage_project",
                                  new_callable=AsyncMock, return_value=can_manage))
        return stack

    def _ss(self):
        ss = MagicMock()
        ss.uuid = "ss-new"
        ss.id = "oid-new"
        ss.title = "Draft"
        ss.save = AsyncMock()
        ss.delete = AsyncMock()
        return ss

    @pytest.mark.asyncio
    async def test_pins_when_project_active_and_manageable(self):
        from app.services.chat_tools import create_extraction_from_document

        ctx = _make_context(active_project_uuid="p1", team_id="team1", user_id="user1")
        ss = self._ss()
        project = _fake_project()
        with self._patches(ss, project, can_manage=True):
            with patch("app.services.project_service.add_pin",
                       new_callable=AsyncMock) as mock_add:
                result = await create_extraction_from_document(
                    ctx, ["d1"], confirmed=True
                )
        mock_add.assert_awaited_once()
        assert result["pinned_to_project"] == "NIH R01"

    @pytest.mark.asyncio
    async def test_no_pin_when_no_active_project(self):
        from app.services.chat_tools import create_extraction_from_document

        ctx = _make_context(team_id="team1", user_id="user1")  # no project
        ss = self._ss()
        with self._patches(ss, project=None, can_manage=False):
            with patch("app.services.project_service.add_pin",
                       new_callable=AsyncMock) as mock_add:
                result = await create_extraction_from_document(
                    ctx, ["d1"], confirmed=True
                )
        mock_add.assert_not_awaited()
        assert result["pinned_to_project"] is None


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import create_project

        ctx = _make_context()
        result = await create_project(ctx, "NSF Grant 2026", "My submission", confirmed=False)

        assert result["needs_confirmation"] is True
        assert result["action"] == "create_project"
        assert "NSF Grant 2026" in result["preview"]

    @pytest.mark.asyncio
    async def test_rejects_empty_title(self):
        from app.services.chat_tools import create_project

        ctx = _make_context()
        result = await create_project(ctx, "   ", confirmed=True)
        assert "title" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_creates_project_when_confirmed(self):
        from app.services.chat_tools import create_project

        fake_project = MagicMock()
        fake_project.uuid = "proj-1"
        fake_project.title = "NSF Grant 2026"
        fake_project.root_folder_uuid = "folder-1"
        fake_project.kb_uuid = "kb-9"
        fake_project.state = "active"

        ctx = _make_context()
        with patch(
            "app.services.project_service.create_project",
            new_callable=AsyncMock,
            return_value=fake_project,
        ) as mock_create:
            result = await create_project(ctx, "NSF Grant 2026", "My submission", confirmed=True)

        assert result["project_uuid"] == "proj-1"
        assert result["kb_uuid"] == "kb-9"
        # The success message must convey the auto-indexing / project-wide chat value
        assert "automatically indexed" in result["message"].lower() or "auto" in result["message"].lower()
        mock_create.assert_awaited_once()


# ---------------------------------------------------------------------------
# check_compliance
# ---------------------------------------------------------------------------


class TestCheckCompliance:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from app.services.chat_tools import check_compliance

        ctx = _make_context()
        with patch("app.services.chat_tools.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)
            result = await check_compliance(ctx, "nope", ["doc-1"])

        assert "error" in result

    @pytest.mark.asyncio
    async def test_unauthorized(self):
        from app.services.chat_tools import check_compliance

        ss = MagicMock()
        ss.verified = False
        ss.user_id = "other-user"
        ss.team_id = "other-team"

        ctx = _make_context(team_id="team1", user_id="user1")
        with patch("app.services.chat_tools.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)
            result = await check_compliance(ctx, "ss-1", ["doc-1"])

        assert "error" in result
        assert "access" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_rules_defined(self):
        from app.services.chat_tools import check_compliance

        ss = MagicMock()
        ss.verified = True
        ss.user_id = "user1"
        ss.team_id = "team1"
        ss.title = "Budget Set"
        ss.normalized_cross_field_rules = MagicMock(return_value=[])

        ctx = _make_context()
        with patch("app.services.chat_tools.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)
            result = await check_compliance(ctx, "ss-1", ["doc-1"])

        assert result["rules_checked"] == 0
        assert "no active compliance rules" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_reports_violations(self):
        from app.services.chat_tools import check_compliance

        ss = MagicMock()
        ss.verified = True
        ss.user_id = "user1"
        ss.team_id = "team1"
        ss.title = "Budget Set"
        ss.normalized_cross_field_rules = MagicMock(
            return_value=[{"id": "r1", "type": "date_order", "enabled": True}]
        )

        fake_validator = MagicMock()
        fake_validator.validate = MagicMock(
            return_value=[
                {
                    "rule": {"type": "date_order"},
                    "rule_id": "r1",
                    "status": "fail",
                    "passed": False,
                    "message": "start_date is after end_date",
                }
            ]
        )

        ctx = _make_context()
        with patch("app.services.chat_tools.SearchSet") as MockSS, \
             patch(
                 "app.services.chat_tools._execute_extraction",
                 new_callable=AsyncMock,
                 return_value={
                     "entities": [{"start_date": "2026-05-01", "end_date": "2026-01-01"}],
                     "documents": ["Award.pdf"],
                 },
             ), \
             patch("app.services.cross_field_validation.CrossFieldValidator", return_value=fake_validator):
            MockSS.find_one = AsyncMock(return_value=ss)
            result = await check_compliance(ctx, "ss-1", ["doc-1"])

        assert result["rules_checked"] == 1
        assert result["documents_checked"] == 1
        assert result["all_compliant"] is False
        assert result["total_violations"] == 1
        assert result["results"][0]["compliant"] is False
        assert result["results"][0]["violations"][0]["rule_type"] == "date_order"

    @pytest.mark.asyncio
    async def test_extraction_error_propagates(self):
        from app.services.chat_tools import check_compliance

        ss = MagicMock()
        ss.verified = True
        ss.user_id = "user1"
        ss.team_id = "team1"
        ss.title = "Budget Set"
        ss.normalized_cross_field_rules = MagicMock(
            return_value=[{"id": "r1", "type": "date_order", "enabled": True}]
        )

        ctx = _make_context()
        with patch("app.services.chat_tools.SearchSet") as MockSS, \
             patch(
                 "app.services.chat_tools._execute_extraction",
                 new_callable=AsyncMock,
                 return_value={"error": "No accessible documents with text content found."},
             ):
            MockSS.find_one = AsyncMock(return_value=ss)
            result = await check_compliance(ctx, "ss-1", ["doc-1"])

        assert "error" in result


# ---------------------------------------------------------------------------
# approve_workflow_step / reject_workflow_step
# ---------------------------------------------------------------------------


def _make_approval(status="pending"):
    from app.models.approval import STATUS_PENDING

    approval = MagicMock()
    approval.uuid = "appr-1"
    approval.status = status or STATUS_PENDING
    approval.step_name = "Manager sign-off"
    approval.workflow_name = "Award Setup"
    approval.assigned_to_user_ids = ["user1"]
    approval.workflow_id = "wf-1"
    approval.workflow_result_id = "wr-1"
    approval.save = AsyncMock()
    return approval


class TestApproveWorkflowStep:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from app.services.chat_tools import approve_workflow_step

        ctx = _make_context()
        with patch("app.models.approval.ApprovalRequest") as MockAR:
            MockAR.find_one = AsyncMock(return_value=None)
            result = await approve_workflow_step(ctx, "appr-1", confirmed=True)

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_non_pending(self):
        from app.services.chat_tools import approve_workflow_step

        ctx = _make_context()
        approval = _make_approval(status="approved")
        with patch("app.models.approval.ApprovalRequest") as MockAR:
            MockAR.find_one = AsyncMock(return_value=approval)
            result = await approve_workflow_step(ctx, "appr-1", confirmed=True)

        assert "error" in result
        assert "status" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_unauthorized(self):
        from app.services.chat_tools import approve_workflow_step

        ctx = _make_context()
        approval = _make_approval()
        with patch("app.models.approval.ApprovalRequest") as MockAR, \
             patch("app.services.chat_tools._can_decide_approval", new_callable=AsyncMock, return_value=False):
            MockAR.find_one = AsyncMock(return_value=approval)
            result = await approve_workflow_step(ctx, "appr-1", confirmed=True)

        assert "error" in result
        assert "authorized" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import approve_workflow_step

        ctx = _make_context()
        approval = _make_approval()
        with patch("app.models.approval.ApprovalRequest") as MockAR, \
             patch("app.services.chat_tools._can_decide_approval", new_callable=AsyncMock, return_value=True):
            MockAR.find_one = AsyncMock(return_value=approval)
            result = await approve_workflow_step(ctx, "appr-1", confirmed=False)

        assert result["needs_confirmation"] is True
        assert "Manager sign-off" in result["preview"]

    @pytest.mark.asyncio
    async def test_approves_when_confirmed(self):
        from app.services.chat_tools import approve_workflow_step

        ctx = _make_context()
        approval = _make_approval()
        fake_celery = MagicMock()
        with patch("app.models.approval.ApprovalRequest") as MockAR, \
             patch("app.services.chat_tools._can_decide_approval", new_callable=AsyncMock, return_value=True), \
             patch("app.celery_app.celery", fake_celery):
            MockAR.find_one = AsyncMock(return_value=approval)
            result = await approve_workflow_step(ctx, "appr-1", confirmed=True)

        assert result["status"] == "approved"
        approval.save.assert_awaited_once()
        fake_celery.send_task.assert_called_once()


class TestRejectWorkflowStep:
    @pytest.mark.asyncio
    async def test_rejects_when_confirmed(self):
        from app.services.chat_tools import reject_workflow_step

        ctx = _make_context()
        approval = _make_approval()
        fake_result = MagicMock()
        fake_result.save = AsyncMock()
        with patch("app.models.approval.ApprovalRequest") as MockAR, \
             patch("app.services.chat_tools._can_decide_approval", new_callable=AsyncMock, return_value=True), \
             patch("app.models.workflow.WorkflowResult") as MockWR:
            MockAR.find_one = AsyncMock(return_value=approval)
            MockWR.get = AsyncMock(return_value=fake_result)
            result = await reject_workflow_step(ctx, "appr-1", comments="missing budget", confirmed=True)

        assert result["status"] == "rejected"
        approval.save.assert_awaited_once()
        assert fake_result.status == "failed"

    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import reject_workflow_step

        ctx = _make_context()
        approval = _make_approval()
        with patch("app.models.approval.ApprovalRequest") as MockAR, \
             patch("app.services.chat_tools._can_decide_approval", new_callable=AsyncMock, return_value=True):
            MockAR.find_one = AsyncMock(return_value=approval)
            result = await reject_workflow_step(ctx, "appr-1", confirmed=False)

        assert result["needs_confirmation"] is True


# ---------------------------------------------------------------------------
# create_automation
# ---------------------------------------------------------------------------


class TestCreateAutomation:
    @pytest.mark.asyncio
    async def test_invalid_trigger_type(self):
        from app.services.chat_tools import create_automation

        ctx = _make_context()
        result = await create_automation(ctx, "Nightly", "workflow", "wf-1", trigger_type="webhook")
        assert "error" in result
        assert "trigger_type" in result["error"]

    @pytest.mark.asyncio
    async def test_folder_watch_requires_folder(self):
        from app.services.chat_tools import create_automation

        ctx = _make_context()
        result = await create_automation(ctx, "Watcher", "workflow", "wf-1", trigger_type="folder_watch")
        assert "error" in result
        assert "folder_uuid" in result["error"]

    @pytest.mark.asyncio
    async def test_schedule_requires_cron(self):
        from app.services.chat_tools import create_automation

        ctx = _make_context()
        result = await create_automation(ctx, "Nightly", "workflow", "wf-1", trigger_type="schedule")
        assert "error" in result
        assert "cron" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_action_type(self):
        from app.services.chat_tools import create_automation

        ctx = _make_context()
        with patch("app.services.access_control.get_authorized_folder", new_callable=AsyncMock) as mock_folder:
            mock_folder.return_value = MagicMock(uuid="f-1", title="Intake")
            result = await create_automation(
                ctx, "Watcher", "task", "x-1", trigger_type="folder_watch", folder_uuid="f-1",
            )
        assert "error" in result
        assert "action_type" in result["error"]

    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import create_automation

        ctx = _make_context()
        with patch("app.services.access_control.get_authorized_folder", new_callable=AsyncMock) as mock_folder, \
             patch("app.services.access_control.get_authorized_workflow", new_callable=AsyncMock) as mock_wf:
            mock_folder.return_value = MagicMock(uuid="f-1", title="Intake")
            mock_wf.return_value = MagicMock(name="Award Setup")
            result = await create_automation(
                ctx, "Watcher", "workflow", "wf-1",
                trigger_type="folder_watch", folder_uuid="f-1", confirmed=False,
            )
        assert result["needs_confirmation"] is True
        assert "Watcher" in result["preview"]

    @pytest.mark.asyncio
    async def test_creates_when_confirmed(self):
        from app.services.chat_tools import create_automation

        fake_auto = MagicMock()
        fake_auto.id = "auto-1"
        fake_auto.name = "Watcher"
        fake_auto.enabled = False

        ctx = _make_context()
        with patch("app.services.access_control.get_authorized_folder", new_callable=AsyncMock) as mock_folder, \
             patch("app.services.access_control.get_authorized_workflow", new_callable=AsyncMock) as mock_wf, \
             patch("app.services.automation_service.create_automation", new_callable=AsyncMock, return_value=fake_auto) as mock_create:
            mock_folder.return_value = MagicMock(uuid="f-1", title="Intake")
            mock_wf.return_value = MagicMock(name="Award Setup")
            result = await create_automation(
                ctx, "Watcher", "workflow", "wf-1",
                trigger_type="folder_watch", folder_uuid="f-1", confirmed=True,
            )

        assert result["id"] == "auto-1"
        assert result["enabled"] is False
        assert "disabled" in result["message"].lower()
        mock_create.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_workflow
# ---------------------------------------------------------------------------


class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_requires_name(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        result = await create_workflow(ctx, "  ", [{"name": "S", "type": "summarize"}])
        assert "error" in result

    @pytest.mark.asyncio
    async def test_requires_steps(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        result = await create_workflow(ctx, "Flow", [])
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_step_type(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        result = await create_workflow(ctx, "Flow", [{"name": "S", "type": "teleport"}])
        assert "error" in result
        assert "unknown type" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_extraction_step_needs_fields(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        result = await create_workflow(ctx, "Flow", [{"name": "Pull", "type": "extraction"}])
        assert "error" in result
        assert "extraction" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_preview_without_confirmation(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        steps = [
            {"name": "Extract budget", "type": "extraction", "extractions": ["amount", "period"]},
            {"name": "Summarize", "type": "summarize"},
        ]
        result = await create_workflow(ctx, "Budget Flow", steps, confirmed=False)
        assert result["needs_confirmation"] is True
        assert "Budget Flow" in result["preview"]
        assert "Extract budget" in result["preview"]

    @pytest.mark.asyncio
    async def test_creates_when_confirmed(self):
        from app.services.chat_tools import create_workflow

        fake_wf = MagicMock()
        fake_wf.id = "wf-9"
        fake_wf.name = "Budget Flow"

        ctx = _make_context()
        steps = [
            {"name": "Extract budget", "type": "extraction", "extractions": ["amount"]},
            {"name": "Summarize", "type": "summarize"},
        ]
        with patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
             patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}) as mock_step, \
             patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value={"id": "t1"}) as mock_task:
            result = await create_workflow(ctx, "Budget Flow", steps, confirmed=True)

        assert result["workflow_id"] == "wf-9"
        assert result["steps_created"] == 2
        assert result["verified"] is False
        # Two steps created, two tasks configured
        assert mock_step.await_count == 2
        assert mock_task.await_count == 2
        # First content step is wired to read the workflow's input documents
        first_task_data = mock_task.await_args_list[0].kwargs["data"]
        assert first_task_data["input_sources"] == ["workflow_documents"]
        # Later step reads the previous step's output
        second_task_data = mock_task.await_args_list[1].kwargs["data"]
        assert second_task_data["input_sources"] == ["step_input"]

    @pytest.mark.asyncio
    async def test_marks_last_step_output_by_default(self):
        from app.services.chat_tools import create_workflow

        fake_wf = MagicMock()
        fake_wf.id = "wf-9"
        fake_wf.name = "Flow"

        ctx = _make_context()
        steps = [{"name": "Summarize", "type": "summarize"}]
        with patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
             patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}) as mock_step, \
             patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value={"id": "t1"}):
            await create_workflow(ctx, "Flow", steps, confirmed=True)

        assert mock_step.await_args_list[0].kwargs["is_output"] is True

    @pytest.mark.asyncio
    async def test_rolls_back_on_failure(self):
        from app.services.chat_tools import create_workflow

        fake_wf = MagicMock()
        fake_wf.id = "wf-9"
        fake_wf.name = "Flow"

        ctx = _make_context()
        steps = [{"name": "Summarize", "type": "summarize"}]
        with patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
             patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}), \
             patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value=None), \
             patch("app.services.workflow_service.delete_workflow", new_callable=AsyncMock) as mock_del:
            result = await create_workflow(ctx, "Flow", steps, confirmed=True)

        assert "error" in result
        mock_del.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_text_input_mode_persists_config(self):
        from app.services.chat_tools import create_workflow

        fake_wf = MagicMock()
        fake_wf.id = "wf-ti"
        fake_wf.name = "Bed Flow"
        fake_wf.save = AsyncMock()

        ctx = _make_context()
        steps = [{"name": "Pull plants", "type": "extraction", "extractions": ["plant", "bed"]}]
        with patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
             patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}), \
             patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value={"id": "t1"}):
            result = await create_workflow(ctx, "Bed Flow", steps, input_mode="text_input", confirmed=True)

        assert result["input_mode"] == "text_input"
        fake_wf.save.assert_awaited_once()
        assert fake_wf.input_config == {"trigger_type": "text_input"}

    @pytest.mark.asyncio
    async def test_text_input_requires_content_step(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        # 'website' fetches a page but is not a content step that reads the input.
        steps = [{"name": "Fetch", "type": "website", "url": "https://example.com"}]
        result = await create_workflow(ctx, "Flow", steps, input_mode="text_input", confirmed=False)

        assert "error" in result
        assert "reads the input" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_input_mode(self):
        from app.services.chat_tools import create_workflow

        ctx = _make_context()
        result = await create_workflow(ctx, "Flow", [{"name": "S", "type": "summarize"}], input_mode="bogus")

        assert "error" in result
        assert "input_mode" in result["error"]
