"""Tests for the KB validation *results* export builder.

``build_kb_validation_results_export`` reshapes a persisted KB ValidationRun's
``result_snapshot`` into the export payload + per-query rows that the
``validation-runs/{run_uuid}/export`` endpoint serves as CSV / XLSX / JSON.
"""

from __future__ import annotations

import csv
import datetime
import io
from types import SimpleNamespace

from app.services.kb_validation_export import (
    EXPORT_FORMAT_TAG,
    RESULT_COLUMNS,
    RUN_META_CSV_COLUMNS,
    build_kb_validation_results_export,
    render_results_csv,
    render_results_xlsx,
)


def _make_kb():
    return SimpleNamespace(
        uuid="kb-1",
        title="NSF PAPPG",
        tags=["v24.1"],
        total_sources=3,
        total_chunks=120,
        resource_config={"seed_id": "kb-nsf-pappg"},
        rag_config_override={"k": 6},
    )


def _make_queries():
    return [
        SimpleNamespace(
            uuid="q-1",
            query="What is the deadline?",
            category="factual",
            expected_answer="30 days after award",
            expected_source_labels=["PAPPG Ch. 2"],
            external_id="ext-1",
        ),
        SimpleNamespace(
            uuid="q-2",
            query="Who signs the budget?",
            category="factual",
            expected_answer="The AOR",
            expected_source_labels=[],
            external_id=None,
        ),
    ]


def _make_vr():
    return SimpleNamespace(
        uuid="run-1234567890",
        score=82.5,
        score_breakdown={"raw_score": 88.0, "final_score": 82.5},
        created_at=datetime.datetime(2026, 8, 1, 12, 30, 0, tzinfo=datetime.timezone.utc),
        result_snapshot={
            "mode": "judge+baseline",
            "judge_model": "claude-x",
            "raw_score": 88.0,
            "num_test_queries": 3,
            "source_health": {"ratio": 1.0},
            "chunk_coverage": {"ratio": 0.9},
            "retrieval_precision": {
                "avg_precision": 0.75,
                "num_queries_judged": 2,
                "num_queries_baselined": 2,
                "avg_judge_score": 0.85,
                "avg_baseline_score": 0.4,
                "avg_lift": 0.45,
                "judge_variance": 0.03,
                "discrimination_summary": {"useful": 2, "redundant": 0, "failing": 0, "other": 0},
                "details": [
                    {
                        # Fully judged query, merged retrieval + judge fields.
                        "query": "What is the deadline?",
                        "query_uuid": "q-1",
                        "category": "factual",
                        "precision": 1.0,
                        "retrieved_sources": ["PAPPG Ch. 2", "PAPPG Ch. 7"],
                        "expected_sources": ["PAPPG Ch. 2"],
                        "answer_match": True,
                        "actual_answer": "The deadline is 30 days after award.",
                        "baseline_answer": "I am not sure.",
                        "judge": {
                            "score": 0.9,
                            "verdict": "PASS",
                            "confidence": 0.95,
                            "reasoning": "Matches the expected answer, cited Ch. 2.",
                            "missing_facts": [],
                            "hallucinated_facts": [],
                        },
                        "baseline_judge": {"score": 0.2, "verdict": "FAIL"},
                        "lift": 0.7,
                        "discrimination": "useful",
                    },
                    {
                        # Judged row keyed only by query text (legacy retrieval
                        # detail without a query_uuid) — expected answer must
                        # still join via the query string.
                        "query": "Who signs the budget?",
                        "precision": 0.5,
                        "retrieved_sources": ["Budget guide"],
                        "expected_sources": [],
                        "answer_match": None,
                        "actual_answer": "The AOR signs it.",
                        "judge": {
                            "score": 0.8,
                            "verdict": "PASS",
                            "confidence": 0.8,
                            "reasoning": "Correct, terse.",
                            "missing_facts": ["countersignature rule"],
                            "hallucinated_facts": [],
                        },
                        "lift": None,
                        "discrimination": "useful",
                    },
                    {
                        # Query deleted since the run; per-query error path.
                        "query": "Deleted question?",
                        "query_uuid": "q-gone",
                        "precision": 0.0,
                        "error": "retrieval blew up",
                    },
                ],
            },
        },
    )


def _build():
    return build_kb_validation_results_export(
        kb=_make_kb(),
        vr=_make_vr(),
        test_queries=_make_queries(),
        catalog_version="1.3.1",
        exported_by_user_id="user-1",
        exported_at="2026-08-03T00:00:00+00:00",
    )


def test_rows_map_judge_and_retrieval_fields():
    _, _, rows = _build()
    assert len(rows) == 3

    r = rows[0]
    assert r["question"] == "What is the deadline?"
    assert r["expected_answer"] == "30 days after award"
    assert r["actual_answer"] == "The deadline is 30 days after award."
    assert r["baseline_answer"] == "I am not sure."
    assert r["judge_score"] == 0.9
    assert r["judge_verdict"] == "PASS"
    assert r["judge_reasoning"] == "Matches the expected answer, cited Ch. 2."
    assert r["baseline_score"] == 0.2
    assert r["lift"] == 0.7
    assert r["discrimination"] == "useful"
    assert r["retrieved_sources"] == ["PAPPG Ch. 2", "PAPPG Ch. 7"]
    assert r["external_id"] == "ext-1"
    assert r["answer_match"] is True


def test_expected_answer_joins_by_query_text_when_uuid_missing():
    _, _, rows = _build()
    r = rows[1]
    assert r["expected_answer"] == "The AOR"
    assert r["query_uuid"] == "q-2"  # recovered from the joined query
    assert r["missing_facts"] == ["countersignature rule"]


def test_deleted_query_exports_blank_expected_answer_and_error():
    _, _, rows = _build()
    r = rows[2]
    assert r["expected_answer"] == ""
    assert r["judge_verdict"] == ""
    assert r["error"] == "retrieval blew up"


def test_run_meta_and_payload_shape():
    payload, run_meta, rows = _build()
    assert payload["format"] == EXPORT_FORMAT_TAG
    assert payload["results"] is rows
    assert payload["knowledge_base"]["title"] == "NSF PAPPG"
    assert run_meta["run_uuid"] == "run-1234567890"
    assert run_meta["judge_model"] == "claude-x"
    assert run_meta["mode"] == "judge+baseline"
    assert run_meta["run_score"] == 82.5
    assert run_meta["catalog_version"] == "1.3.1"
    assert run_meta["kb_seed_id"] == "kb-nsf-pappg"
    assert run_meta["avg_lift"] == 0.45
    assert run_meta["source_health_ratio"] == 1.0
    assert run_meta["rag_config_override_current"] == {"k": 6}
    assert run_meta["run_created_at"] == "2026-08-01T12:30:00+00:00"


def test_csv_repeats_run_meta_and_joins_lists():
    _, run_meta, rows = _build()
    text = render_results_csv(run_meta, rows)
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == RUN_META_CSV_COLUMNS + RESULT_COLUMNS
    assert len(parsed) == 4  # header + 3 queries
    first = dict(zip(parsed[0], parsed[1]))
    assert first["run_uuid"] == "run-1234567890"
    assert first["kb_title"] == "NSF PAPPG"
    assert first["retrieved_sources"] == "PAPPG Ch. 2; PAPPG Ch. 7"
    # Every row repeats the run metadata so multi-run CSVs concatenate cleanly.
    third = dict(zip(parsed[0], parsed[3]))
    assert third["run_uuid"] == "run-1234567890"
    assert third["error"] == "retrieval blew up"


def test_xlsx_round_trips_summary_and_results():
    from openpyxl import load_workbook

    _, run_meta, rows = _build()
    data = render_results_xlsx(run_meta, rows)
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Summary", "Results"]

    summary = {r[0].value: r[1].value for r in wb["Summary"].iter_rows(min_row=2)}
    assert summary["run_uuid"] == "run-1234567890"
    assert summary["judge_model"] == "claude-x"

    results = wb["Results"]
    header = [c.value for c in results[1]]
    assert header == RESULT_COLUMNS
    body = list(results.iter_rows(min_row=2, values_only=True))
    assert len(body) == 3
    first = dict(zip(header, body[0]))
    assert first["question"] == "What is the deadline?"
    assert first["judge_score"] == 0.9


def test_xlsx_strips_illegal_control_characters():
    from openpyxl import load_workbook

    _, run_meta, rows = _build()
    rows[0]["actual_answer"] = "bad\x00control\x08chars kept text"
    data = render_results_xlsx(run_meta, rows)
    wb = load_workbook(io.BytesIO(data))
    results = wb["Results"]
    header = [c.value for c in results[1]]
    first = dict(zip(header, next(results.iter_rows(min_row=2, values_only=True))))
    assert first["actual_answer"] == "badcontrolchars kept text"
