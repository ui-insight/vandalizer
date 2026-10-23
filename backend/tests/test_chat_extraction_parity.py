"""Chat's run_extraction is the editor's run.

Support ticket: "NSF Subaward UI-BSU-2024-0847 Extraction" on
subaward-agreement.pdf gave different values in chat and in the editor
(Agreement Type, Governing Regulation, "1." / "D1." prefixes, a missing D4 due
date), 27 chat values had no source while every editor value had a page, and
the chat run showed 0 ms in History and couldn't be opened. Chat ran its own
copy of the engine call: the set's raw config instead of the optimizer's,
domain prompt hints the editor never uses, no model, and an activity logged
with start == finish and no result snapshot.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_chat_tools import _make_context, _make_doc


def _search_set():
    ss = MagicMock()
    ss.uuid = "ss-1"
    ss.title = "NSF Subaward UI-BSU-2024-0847 Extraction"
    ss.verified = False
    ss.user_id = "user1"
    ss.team_id = "team1"
    ss.domain = "nsf"
    ss.extraction_config = {"mode": "one_pass"}
    ss.extraction_config_override = {"mode": "two_pass"}
    item = MagicMock(searchphrase="Agreement Type", is_optional=False, enum_values=None)
    ss.get_extraction_items = AsyncMock(return_value=[item])
    return ss


def _no_validation_runs():
    chain = MagicMock()
    chain.sort.return_value.first_or_none = AsyncMock(return_value=None)
    return chain


EDITOR_RUN = {
    "results": [{"Agreement Type": "Federal Research Subaward under 2 CFR 200"}],
    "sources": [{"Agreement Type": {
        "quote": "This Federal Research Subaward under 2 CFR 200", "page": 1,
        "verified": True, "value_supported": True, "support": "supported",
        "document_uuid": "doc-1", "document_title": "subaward-agreement.pdf",
    }}],
    "cross_field": None,
    "cross_field_sets": [None],
    "document_warnings": [{
        "document_uuid": "doc-1", "title": "subaward-agreement.pdf",
        "codes": ["truncated"], "text": "Only part of this document was read.",
    }],
    "activity_id": "activity-1",
}


async def _run_chat(run_result):
    from app.services.chat_tools import run_extraction

    ctx = _make_context(model_name="kimi-k3")
    # The run is recorded against the chat it ran in, so History can nest it.
    ctx.deps.conversation.uuid = "conv-1"
    recorded = AsyncMock(return_value=run_result)
    with (
        patch("app.services.chat_tools.SearchSet") as MockSS,
        patch("app.services.chat_tools.SmartDocument") as MockDoc,
        patch("app.services.chat_tools.ValidationRun") as MockRun,
        patch("app.routers.extractions.run_recorded_extraction", recorded),
        patch("app.services.user_memory_service.record_extraction", new=AsyncMock()),
    ):
        MockSS.find_one = AsyncMock(return_value=_search_set())
        MockDoc.find_one = AsyncMock(return_value=_make_doc(uuid="doc-1", title="subaward-agreement.pdf"))
        MockRun.find.return_value = _no_validation_runs()
        result = await run_extraction(ctx, "ss-1", ["doc-1"])
    return result, recorded


class TestChatRunsTheEditorRun:
    @pytest.mark.asyncio
    async def test_delegates_to_the_recorded_editor_run(self):
        result, recorded = await _run_chat(EDITOR_RUN)

        recorded.assert_awaited_once()
        args, kwargs = recorded.await_args
        assert args[0].uuid == "ss-1"
        assert args[1] == ["doc-1"]
        assert kwargs == {
            "user_id": "user1", "team_id": "team1",
            "model": "kimi-k3", "tags": ["chat"],
            "source_conversation_id": "conv-1",
        }
        assert result["activity_id"] == "activity-1"

    @pytest.mark.asyncio
    async def test_reports_the_editor_values_and_sources(self):
        result, _ = await _run_chat(EDITOR_RUN)

        assert result["entities"] == EDITOR_RUN["results"]
        src = result["sources"][0]["Agreement Type"]
        assert src["page"] == 1
        assert src["verified"] is True
        assert src["support"] == "supported"
        assert result["source_coverage"] == {
            "fields_with_verified_source": 1, "fields_without_verified_source": 0,
        }
        assert "source_note" not in result
        assert "Only part of this document was read." in result["note"]

    @pytest.mark.asyncio
    async def test_a_run_with_no_values_is_reported_as_failed(self):
        result, _ = await _run_chat({
            **EDITOR_RUN, "results": [{"Agreement Type": None}], "sources": [{}],
            "error": "Extraction returned no values",
        })
        assert result["error"].startswith("Extraction returned no values")
        assert "entities" not in result


class TestRecordedRun:
    """The editor's run, now shared: it records a real run in History."""

    def _svc(self, results):
        svc = MagicMock()
        svc.run_extraction_sync = AsyncMock(return_value=results)
        return svc

    def _activity(self):
        activity = MagicMock()
        activity.activity_start = AsyncMock(return_value=MagicMock(id="activity-1"))
        activity.activity_finish = AsyncMock()
        activity.activity_update = AsyncMock()
        return activity

    @pytest.mark.asyncio
    async def test_records_start_finish_and_an_openable_snapshot(self):
        from app.models.activity import ActivityStatus
        from app.routers.extractions import run_recorded_extraction
        from app.services.extraction_sources import SOURCE_KEY

        svc = self._svc([{
            "Agreement Type": "Federal Research Subaward under 2 CFR 200",
            SOURCE_KEY: {"Agreement Type": {"quote": "q", "page": 1, "verified": True}},
        }])
        activity = self._activity()
        with (
            patch("app.routers.extractions.svc", svc),
            patch("app.routers.extractions.activity_service", activity),
            patch("app.tasks.quality_tasks.auto_validate_extraction") as auto_validate,
        ):
            run = await run_recorded_extraction(
                _search_set(), ["doc-1"], user_id="user1", team_id="team1",
                model="kimi-k3", tags=["chat"],
            )

        start = activity.activity_start.await_args.kwargs
        assert start["tags"] == ["chat"]
        assert start["search_set_uuid"] == "ss-1"
        assert svc.run_extraction_sync.await_args.kwargs["model"] == "kimi-k3"
        assert svc.run_extraction_sync.await_args.kwargs["capture_sources"] is True
        activity.activity_finish.assert_awaited_once_with("activity-1", ActivityStatus.COMPLETED)
        snapshot = activity.activity_update.await_args.kwargs["result_snapshot"]
        assert snapshot["normalized"] == {"Agreement Type": "Federal Research Subaward under 2 CFR 200"}
        assert snapshot["sources"]["Agreement Type"]["page"] == 1
        assert run["activity_id"] == "activity-1"
        auto_validate.delay.assert_called_once_with("ss-1", "user1", "kimi-k3")

    @pytest.mark.asyncio
    async def test_a_cancelled_run_is_not_left_running(self):
        import asyncio

        from app.models.activity import ActivityStatus
        from app.routers.extractions import run_recorded_extraction

        svc = MagicMock()
        svc.run_extraction_sync = AsyncMock(side_effect=asyncio.CancelledError)
        activity = self._activity()
        with (
            patch("app.routers.extractions.svc", svc),
            patch("app.routers.extractions.activity_service", activity),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_recorded_extraction(_search_set(), ["doc-1"], user_id="user1", team_id=None)

        args, kwargs = activity.activity_finish.await_args
        assert args == ("activity-1", ActivityStatus.FAILED)
        assert "cancelled" in kwargs["error"]


class TestProposeTestCaseUsesEditorSettings:
    @pytest.mark.asyncio
    async def test_engine_gets_optimizer_config_chat_model_and_no_domain(self):
        from app.services.chat_tools import propose_test_case

        engine = MagicMock()
        engine.extract.return_value = [{"Agreement Type": "Federal Research Subaward under 2 CFR 200"}]
        Engine = MagicMock(return_value=engine)
        ctx = _make_context(model_name="kimi-k3")
        with (
            patch("app.services.chat_tools.SearchSet") as MockSS,
            patch("app.services.chat_tools.SmartDocument") as MockDoc,
            patch("app.services.extraction_engine.ExtractionEngine", Engine),
            patch("app.services.chat_tools.VerificationSession") as MockSession,
        ):
            MockSS.find_one = AsyncMock(return_value=_search_set())
            MockDoc.find_one = AsyncMock(return_value=_make_doc(uuid="doc-1"))
            MockSession.return_value.insert = AsyncMock()
            await propose_test_case(ctx, "ss-1", "doc-1")

        assert "domain" not in Engine.call_args.kwargs
        kwargs = engine.extract.call_args.kwargs
        assert kwargs["model"] == "kimi-k3"
        assert kwargs["extraction_config_override"] == {"mode": "two_pass"}


class TestUnscoredBadge:
    """v5 retest ticket: an extraction never validated showed no badge, while
    the user guide says anything unvalidated is labelled Unscored."""

    @pytest.mark.asyncio
    async def test_a_set_with_no_validation_run_is_unscored(self):
        result, _ = await _run_chat(EDITOR_RUN)

        assert result["quality"]["tier"] == "unscored"
        assert result["quality"]["score"] is None


class TestWorkflowUnscored:
    @pytest.mark.asyncio
    async def test_a_workflow_with_no_validation_run_is_unscored(self):
        from app.services import chat_tools

        chain = MagicMock()
        chain.sort.return_value.first_or_none = AsyncMock(return_value=None)
        with patch.object(chat_tools, "ValidationRun") as MockRun:
            MockRun.find.return_value = chain
            quality = await chat_tools._workflow_quality_sidecar("wf-1", MagicMock())

        assert quality["tier"] == "unscored"
        assert quality["score"] is None


class TestAFailedRunSaysWhy:
    """#1035: the editor's run turns an engine failure into an HTTPException
    carrying a reason the user can act on. Chat's run_extraction only caught
    ExtractionError, which no longer reaches it, and told the model to
    "suggest retrying" — wrong for a structured-output rejection, where the
    same request on the same model fails the same way."""

    async def _chat_with_failure(self, exc):
        from app.services.chat_tools import run_extraction

        ctx = _make_context(model_name="kimi-k3")
        ctx.deps.conversation.uuid = "conv-1"
        with (
            patch("app.services.chat_tools.SearchSet") as MockSS,
            patch("app.services.chat_tools.SmartDocument") as MockDoc,
            patch("app.routers.extractions.run_recorded_extraction", AsyncMock(side_effect=exc)),
        ):
            MockSS.find_one = AsyncMock(return_value=_search_set())
            MockDoc.find_one = AsyncMock(return_value=_make_doc(uuid="doc-1", title="award.pdf"))
            return await run_extraction(ctx, "ss-1", ["doc-1"])

    @pytest.mark.asyncio
    async def test_a_rejected_request_relays_the_reason_and_no_retry(self):
        from fastapi import HTTPException

        reason = "The model server (kimi-k3) rejected this extraction's structured-output request"
        out = await self._chat_with_failure(HTTPException(status_code=502, detail=reason))
        assert reason in out["error"]
        assert "Do not suggest simply retrying" in out["hint"]

    @pytest.mark.asyncio
    async def test_an_outage_suggests_running_again(self):
        from fastapi import HTTPException

        out = await self._chat_with_failure(HTTPException(status_code=503, detail="couldn't be reached"))
        assert "running it again in a moment" in out["hint"]

    @pytest.mark.asyncio
    async def test_a_raw_engine_error_is_described_too(self):
        from app.services.extraction_engine import ExtractionError

        out = await self._chat_with_failure(ExtractionError("maximum context length is 8192 tokens"))
        assert "too long for the selected model" in out["error"]
        assert "Do not suggest simply retrying" in out["hint"]


@pytest.mark.asyncio
async def test_an_unrecognized_failure_is_logged_with_its_set_and_reported():
    # The merge brought #1035's logging into v5's shared run, where it named
    # a ``req`` that doesn't exist there: an unrecognized failure raised
    # NameError instead of the reason.
    from fastapi import HTTPException

    from app.routers.extractions import run_recorded_extraction

    svc = MagicMock()
    svc.run_extraction_sync = AsyncMock(side_effect=RuntimeError("parser exploded"))
    activity = MagicMock()
    activity.activity_start = AsyncMock(return_value=MagicMock(id="activity-1"))
    activity.activity_finish = AsyncMock()
    with (
        patch("app.routers.extractions.svc", svc),
        patch("app.routers.extractions.activity_service", activity),
        patch("app.routers.extractions.logger") as logger,
        pytest.raises(HTTPException) as raised,
    ):
        await run_recorded_extraction(_search_set(), ["doc-1"], user_id="user1", team_id=None)

    assert raised.value.status_code == 500
    assert "parser exploded" in raised.value.detail
    assert logger.exception.call_args.args[1] == "ss-1"
