"""Module 4 (Extraction Engine) grading: fields from standalone Extractions.

Regression coverage for the bug where a user's comprehensive Extraction
(a standalone SearchSet built in the Extraction editor) was not counted —
the grader only scanned Workflow Extraction tasks, so a 26-field extraction
showed up as "8 unique fields" with present fields flagged as missing.

The model symbols are patched wholesale so the validators can run without an
initialized Beanie connection (field-expression queries need one otherwise).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import certification_service as cs


def _query(items):
    """Mimic a Beanie query: an object with an async `.to_list()`."""
    q = MagicMock()
    q.to_list = AsyncMock(return_value=items)
    return q


def _model(items):
    """Stand in for a Beanie model class: `.find(...)` returns a query."""
    m = MagicMock()
    m.find.return_value = _query(items)
    return m


def test_union_fields_dedupes_case_insensitively_preserving_order():
    out = cs._union_fields(["PI Name", "Institution"], ["institution", "Grant Number"])
    assert out == ["PI Name", "Institution", "Grant Number"]


async def test_collect_searchset_fields_reads_standalone_extraction():
    ss = SimpleNamespace(uuid="ss-1")
    items = [
        SimpleNamespace(title="Personnel Costs", searchphrase="What are the personnel costs?"),
        SimpleNamespace(title=None, searchphrase="Travel Costs"),       # falls back to searchphrase
        SimpleNamespace(title="personnel costs", searchphrase="dup"),    # case-insensitive duplicate
        SimpleNamespace(title="   ", searchphrase=""),                   # empty -> skipped
    ]
    with patch.object(cs, "SearchSet", _model([ss])), \
         patch.object(cs, "SearchSetItem", _model(items)):
        names = await cs._collect_searchset_fields("user-1")
    assert names == ["Personnel Costs", "Travel Costs"]


async def test_validate_extraction_engine_counts_standalone_extraction():
    # No workflows at all; 16 fields live only in a standalone SearchSet.
    field_items = [SimpleNamespace(title=f"Field {i}", searchphrase=f"phrase {i}") for i in range(16)]
    ss = SimpleNamespace(uuid="ss-1")
    with patch.object(cs, "Workflow", _model([])), \
         patch.object(cs, "SearchSet", _model([ss])), \
         patch.object(cs, "SearchSetItem", _model(field_items)):
        result = await cs._validate_extraction_engine("user-1")
    assert result["passed"] is True
    field_check = next(c for c in result["checks"] if c["name"] == "15+ extraction fields")
    assert field_check["passed"] is True
    assert "16 unique fields" in field_check["detail"]


async def test_validate_extraction_engine_matches_expected_field_names():
    # Real expected field names, defined only in a standalone Extraction.
    titles = ["PI Name", "Institution", "Personnel Costs", "Equipment Costs", "Travel Costs"]
    items = [SimpleNamespace(title=t, searchphrase=t) for t in titles]
    ss = SimpleNamespace(uuid="ss-1")
    with patch.object(cs, "Workflow", _model([])), \
         patch.object(cs, "SearchSet", _model([ss])), \
         patch.object(cs, "SearchSetItem", _model(items)):
        result = await cs._validate_extraction_engine("user-1")
    field_check = next(c for c in result["checks"] if c["name"] == "15+ extraction fields")
    # All five titles are in the exercise's expected_fields list.
    assert "matched 5/20 expected" in field_check["detail"]


# ---------------------------------------------------------------------------
# Module: Batch Processing
#
# Regression for the bug where the grader queried WorkflowResult.user_id — a
# field that doesn't exist — which raised and surfaced to the user as
# "the module cannot be verified, try again later", making it unpassable.
# Batch results are scoped via the user's workflows instead.
# ---------------------------------------------------------------------------


async def test_validate_batch_processing_passes_on_completed_batch_of_three():
    workflows = [SimpleNamespace(id="wf-1")]
    batch = [
        SimpleNamespace(batch_id="b1", status="completed", workflow="wf-1"),
        SimpleNamespace(batch_id="b1", status="completed", workflow="wf-1"),
        SimpleNamespace(batch_id="b1", status="completed", workflow="wf-1"),
    ]
    with patch.object(cs, "Workflow", _model(workflows)), \
         patch.object(cs, "WorkflowResult", _model(batch)):
        result = await cs._validate_batch_processing("user-1")
    assert result["passed"] is True
    assert all(c["passed"] for c in result["checks"])


async def test_validate_batch_processing_no_workflows_does_not_raise():
    # The original bug raised AttributeError here; now it returns a clean
    # "not passed" result instead of a 500.
    with patch.object(cs, "Workflow", _model([])), \
         patch.object(cs, "WorkflowResult", _model([])):
        result = await cs._validate_batch_processing("user-1")
    assert result["passed"] is False
    assert result["stars"] == 0


async def test_validate_batch_processing_fails_when_a_doc_did_not_complete():
    workflows = [SimpleNamespace(id="wf-1")]
    batch = [
        SimpleNamespace(batch_id="b1", status="completed", workflow="wf-1"),
        SimpleNamespace(batch_id="b1", status="completed", workflow="wf-1"),
        SimpleNamespace(batch_id="b1", status="queued", workflow="wf-1"),
    ]
    with patch.object(cs, "Workflow", _model(workflows)), \
         patch.object(cs, "WorkflowResult", _model(batch)):
        result = await cs._validate_batch_processing("user-1")
    # Batch size of 3 passes the first check, but "All succeeded" fails.
    all_ok = next(c for c in result["checks"] if c["name"] == "All succeeded")
    assert all_ok["passed"] is False
    assert result["passed"] is False
