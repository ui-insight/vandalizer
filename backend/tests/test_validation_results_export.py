"""Tests for the extraction validation *results* export builder.

``_build_validation_results_export`` reshapes a persisted ValidationRun's
``result_snapshot`` into the export payload + tidy CSV rows that the
``download-results`` endpoint zips up — the raw extracted value for every
replicate of every document.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from app.routers.extractions import _build_validation_results_export


def _make_vr():
    return SimpleNamespace(
        uuid="run-1",
        created_at=datetime.datetime(2026, 6, 15, 18, 0, 0, tzinfo=datetime.timezone.utc),
        model="claude-x",
        num_runs=3,
        num_test_cases=1,
        accuracy=0.83,
        consistency=0.9,
        score=82.0,
        result_snapshot={
            "num_runs": 3,
            "aggregate_accuracy": 0.83,
            "aggregate_consistency": 0.9,
            "test_cases": [
                {
                    "uuid": "tc-1",
                    "label": "Doc A",
                    "overall_accuracy": 0.83,
                    "overall_consistency": 0.9,
                    "per_run_correct": [1, 1, 0],
                    "fields": [
                        {
                            "field_name": "title",
                            "expected": "Hello",
                            "extracted_values": ["Hello", "Hello", "Hola"],
                            "most_common_value": "Hello",
                            "accuracy": 0.67,
                            "consistency": 0.67,
                            "error_types": {"wrong_value": 1},
                        },
                        {
                            "field_name": "amount",
                            "expected": None,
                            "extracted_values": ["10", None, "10"],
                            "most_common_value": "10",
                            "accuracy": None,
                            "consistency": 0.67,
                            "error_types": {},
                        },
                    ],
                }
            ],
        },
    )


def _build(doc_by_case=None):
    return _build_validation_results_export(
        ss_uuid="ss-1",
        ss_title="My Set",
        vr=_make_vr(),
        doc_by_case=doc_by_case if doc_by_case is not None else {},
        exported_by_user_id="u1",
        exported_at="2026-06-15T18:00:00+00:00",
    )


def test_payload_envelope_and_run_metadata():
    payload, _ = _build()
    assert payload["format"] == "vandalizer.validation-results.v1"
    assert payload["search_set"] == {"uuid": "ss-1", "title": "My Set"}
    run = payload["validation_run"]
    assert run["uuid"] == "run-1"
    assert run["num_runs"] == 3
    assert run["model"] == "claude-x"
    assert run["created_at"].endswith("+00:00")


def test_replicates_are_one_per_run_in_order():
    payload, _ = _build()
    title_field = payload["documents"][0]["fields"][0]
    assert title_field["field_name"] == "title"
    assert title_field["replicates"] == [
        {"run": 1, "value": "Hello"},
        {"run": 2, "value": "Hello"},
        {"run": 3, "value": "Hola"},
    ]


def test_document_uuid_recovered_from_join():
    payload, _ = _build(doc_by_case={"tc-1": {"document_uuid": "doc-9", "source_type": "document"}})
    doc = payload["documents"][0]
    assert doc["document_uuid"] == "doc-9"
    assert doc["source_type"] == "document"


def test_document_uuid_none_when_case_missing():
    payload, _ = _build()  # empty join map
    assert payload["documents"][0]["document_uuid"] is None


def test_csv_rows_one_per_document_field_replicate():
    _, csv_rows = _build(doc_by_case={"tc-1": {"document_uuid": "doc-9", "source_type": "document"}})
    # 2 fields x 3 replicates = 6 rows
    assert len(csv_rows) == 6
    # Columns: test_case_uuid, label, document_uuid, field_name, expected, run, value
    assert csv_rows[0] == ["tc-1", "Doc A", "doc-9", "title", "Hello", 1, "Hello"]
    # None expected and None value both render as empty string.
    amount_rows = [r for r in csv_rows if r[3] == "amount"]
    assert amount_rows[0] == ["tc-1", "Doc A", "doc-9", "amount", "", 1, "10"]
    assert amount_rows[1] == ["tc-1", "Doc A", "doc-9", "amount", "", 2, ""]


def test_tolerates_sources_key_and_missing_snapshot():
    vr = _make_vr()
    vr.result_snapshot = {"sources": vr.result_snapshot["test_cases"], "num_runs": 3}
    payload, csv_rows = _build_validation_results_export(
        ss_uuid="ss-1", ss_title="My Set", vr=vr, doc_by_case={},
        exported_by_user_id="u1", exported_at="2026-06-15T18:00:00+00:00",
    )
    assert len(payload["documents"]) == 1
    assert len(csv_rows) == 6

    vr.result_snapshot = {}
    payload2, csv_rows2 = _build_validation_results_export(
        ss_uuid="ss-1", ss_title="My Set", vr=vr, doc_by_case={},
        exported_by_user_id="u1", exported_at="2026-06-15T18:00:00+00:00",
    )
    assert payload2["documents"] == []
    assert csv_rows2 == []
