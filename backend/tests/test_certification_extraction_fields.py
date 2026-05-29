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
