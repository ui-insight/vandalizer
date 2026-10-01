"""The workflow optimizer must not tune against documents with no text.

A test input is a past run marked "expected output"; the optimizer re-runs
the workflow on that run's documents for every trial. When a document has
since been deleted or lost its text, every trial ran the workflow on nothing
and the judge scored the emptiness — the whole budget spent on meaningless
scores, and the "winner" possibly applied (Sentry 7598676926: "None of the 1
input documents have raw_text available", once per trial).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_optimizer as wo


def _wf():
    return SimpleNamespace(
        id="wf-1",
        validation_plan=[{"id": "c1"}],
        validation_inputs=[
            {"type": "expected_output", "id": "vi-ok", "session_id": "s-ok", "output_text": "A"},
            {"type": "expected_output", "id": "vi-gone", "session_id": "s-gone", "output_text": "B"},
            {"type": "expected_output", "id": "vi-half", "session_id": "s-half", "output_text": "C"},
        ],
    )


_DOCS = {"s-ok": ["d-ok"], "s-gone": ["d-gone"], "s-half": ["d-ok", "d-gone"]}


async def _find_result(query):
    return SimpleNamespace(input_context={"doc_uuids": _DOCS[query["session_id"]]})


def _patched(readable):
    result_cls = MagicMock()
    result_cls.find_one = AsyncMock(side_effect=_find_result)
    return (
        patch.object(wo, "WorkflowResult", result_cls),
        patch.object(wo, "_readable_document_uuids", AsyncMock(return_value=set(readable))),
    )


@pytest.mark.asyncio
async def test_inputs_with_an_unreadable_document_are_dropped_and_reported():
    p_result, p_readable = _patched({"d-ok"})
    unreadable: list[dict] = []
    with p_result, p_readable:
        inputs = await wo._resolve_test_inputs(_wf(), unreadable)

    assert [ti["id"] for ti in inputs] == ["vi-ok"]
    # vi-half's expected output came from both documents; one alone would be
    # scored against an answer it could never reproduce.
    assert [u["id"] for u in unreadable] == ["vi-gone", "vi-half"]


@pytest.mark.asyncio
async def test_readable_inputs_are_all_kept():
    p_result, p_readable = _patched({"d-ok", "d-gone"})
    with p_result, p_readable:
        inputs = await wo._resolve_test_inputs(_wf())
    assert [ti["id"] for ti in inputs] == ["vi-ok", "vi-gone", "vi-half"]


@pytest.mark.asyncio
async def test_a_run_whose_documents_are_all_unreadable_fails_before_any_trial():
    run_doc = MagicMock(status="queued")
    run_doc.save = AsyncMock()
    run_cls = MagicMock()
    run_cls.find_one = AsyncMock(return_value=run_doc)
    wf_cls = MagicMock()
    wf_cls.get = AsyncMock(return_value=_wf())

    p_result, p_readable = _patched(set())
    with p_result, p_readable, \
         patch.object(wo, "WorkflowOptimizationRun", run_cls), \
         patch.object(wo, "Workflow", wf_cls), \
         patch.object(wo, "_update", AsyncMock()), \
         patch.object(wo, "notify_run_terminal", AsyncMock()), \
         patch.object(wo, "_run_single_trial", AsyncMock()) as trial:
        out = await wo.run_optimization(
            workflow_id="507f1f77bcf86cd799439011", user_id="u1", run_uuid="r1",
        )

    assert out.status == "failed"
    assert "3 expected-output runs' documents were deleted or have no extracted text" in out.error_message
    trial.assert_not_awaited()


def test_the_message_names_the_count_and_reads_correctly():
    assert wo.no_test_inputs_message(0).startswith("No test inputs available.")
    assert "1 expected-output run's document was deleted or has no extracted text" in (
        wo.no_test_inputs_message(1)
    )
