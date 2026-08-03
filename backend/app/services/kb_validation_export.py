"""Builders for exporting KB validation run results (CSV / XLSX / JSON).

A persisted ``ValidationRun`` for a knowledge base keeps the full per-query
judge output in ``result_snapshot.retrieval_precision.details`` — question,
actual answer, judge score/verdict/reasoning, retrieved sources, baseline and
lift. The snapshot does *not* keep the expected answer (the judge reads it
from the live ``KBTestQuery`` at run time), so the builder re-joins the
current test queries by uuid (falling back to the query text) to fill it in;
a since-deleted query simply exports with a blank expected answer.

The build step is pure (no I/O) so it's unit-testable, matching the
extraction-results export in ``routers/extractions.py``.
"""

from __future__ import annotations

from typing import Any

EXPORT_FORMAT_TAG = "vandalizer.kb-validation-results.v1"

# Run-level metadata repeated on every CSV row so evaluators can concatenate
# exports from several runs (or several KBs) into one comparison table.
RUN_META_CSV_COLUMNS = [
    "run_uuid",
    "run_created_at",
    "kb_uuid",
    "kb_title",
    "mode",
    "judge_model",
    "run_score",
]

# Per-query columns, in export order. List-valued cells ("; "-joined in
# CSV/XLSX) stay native lists in the JSON payload.
RESULT_COLUMNS = [
    "query_uuid",
    "external_id",
    "question",
    "category",
    "expected_answer",
    "expected_sources",
    "retrieved_sources",
    "retrieval_precision",
    "answer_match",
    "actual_answer",
    "judge_score",
    "judge_verdict",
    "judge_confidence",
    "judge_reasoning",
    "missing_facts",
    "hallucinated_facts",
    "baseline_answer",
    "baseline_score",
    "baseline_verdict",
    "lift",
    "discrimination",
    "error",
]


def build_kb_validation_results_export(
    *,
    kb,
    vr,
    test_queries: list,
    catalog_version: str | None,
    exported_by_user_id: str,
    exported_at: str,
) -> tuple[dict, dict, list[dict]]:
    """Reshape a persisted KB ValidationRun into export structures.

    Returns ``(json_payload, run_meta, rows)``: ``rows`` is one dict per test
    query (keys = ``RESULT_COLUMNS``), ``run_meta`` the run-level metadata,
    and ``json_payload`` the full structured export combining both.
    """
    snap = vr.result_snapshot or {}
    rp = snap.get("retrieval_precision") or {}
    details = rp.get("details") or []

    by_uuid = {q.uuid: q for q in test_queries}
    by_text = {q.query: q for q in test_queries}

    rows: list[dict] = []
    for det in details:
        quuid = det.get("query_uuid") or ""
        tq = by_uuid.get(quuid) or by_text.get(det.get("query") or "")
        judge = det.get("judge") or {}
        baseline = det.get("baseline_judge") or {}
        rows.append({
            "query_uuid": quuid or (getattr(tq, "uuid", "") if tq else ""),
            "external_id": (getattr(tq, "external_id", None) if tq else None) or "",
            "question": det.get("query") or "",
            "category": det.get("category")
                or (getattr(tq, "category", None) if tq else None) or "",
            "expected_answer": (getattr(tq, "expected_answer", None) if tq else None) or "",
            "expected_sources": det.get("expected_sources")
                or (list(getattr(tq, "expected_source_labels", []) or []) if tq else []),
            "retrieved_sources": det.get("retrieved_sources") or [],
            "retrieval_precision": det.get("precision"),
            "answer_match": det.get("answer_match"),
            "actual_answer": det.get("actual_answer") or "",
            "judge_score": judge.get("score"),
            "judge_verdict": judge.get("verdict") or "",
            "judge_confidence": judge.get("confidence"),
            "judge_reasoning": judge.get("reasoning") or "",
            "missing_facts": judge.get("missing_facts") or [],
            "hallucinated_facts": judge.get("hallucinated_facts") or [],
            "baseline_answer": det.get("baseline_answer") or "",
            "baseline_score": baseline.get("score"),
            "baseline_verdict": baseline.get("verdict") or "",
            "lift": det.get("lift"),
            "discrimination": det.get("discrimination") or "",
            "error": det.get("error") or "",
        })

    run_meta = {
        "run_uuid": vr.uuid,
        "run_created_at": vr.created_at.isoformat() if getattr(vr, "created_at", None) else None,
        "kb_uuid": kb.uuid,
        "kb_title": kb.title,
        "mode": snap.get("mode"),
        "judge_model": snap.get("judge_model"),
        "run_score": vr.score,
        "raw_score": snap.get("raw_score"),
        "score_breakdown": getattr(vr, "score_breakdown", None) or None,
        "num_test_queries": snap.get("num_test_queries"),
        "num_queries_judged": rp.get("num_queries_judged"),
        "num_queries_baselined": rp.get("num_queries_baselined"),
        "avg_judge_score": rp.get("avg_judge_score"),
        "avg_baseline_score": rp.get("avg_baseline_score"),
        "avg_lift": rp.get("avg_lift"),
        "judge_variance": rp.get("judge_variance"),
        "avg_retrieval_precision": rp.get("avg_precision"),
        "discrimination_summary": rp.get("discrimination_summary"),
        "source_health_ratio": (snap.get("source_health") or {}).get("ratio"),
        "chunk_coverage_ratio": (snap.get("chunk_coverage") or {}).get("ratio"),
        "catalog_version": catalog_version,
        "kb_seed_id": (getattr(kb, "resource_config", None) or {}).get("seed_id"),
        # The KB's RAG override as of export time. Validation runs don't
        # snapshot the config they ran under, so for historical runs this may
        # differ from what the run actually used — hence the explicit name.
        "rag_config_override_current": getattr(kb, "rag_config_override", None),
    }

    payload = {
        "format": EXPORT_FORMAT_TAG,
        "exported_at": exported_at,
        "exported_by_user_id": exported_by_user_id,
        "knowledge_base": {
            "uuid": kb.uuid,
            "title": kb.title,
            "tags": list(getattr(kb, "tags", []) or []),
            "total_sources": getattr(kb, "total_sources", None),
            "total_chunks": getattr(kb, "total_chunks", None),
        },
        "validation_run": run_meta,
        "results": rows,
    }
    return payload, run_meta, rows


def _flatten_cell(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return value


def render_results_csv(run_meta: dict, rows: list[dict]) -> str:
    """One row per test query, with run-level columns repeated for easy
    cross-run concatenation. Values containing separators/newlines are quoted
    by the csv module."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(RUN_META_CSV_COLUMNS + RESULT_COLUMNS)
    meta_cells = [_flatten_cell(run_meta.get(k)) for k in RUN_META_CSV_COLUMNS]
    for row in rows:
        writer.writerow(
            meta_cells + [_flatten_cell(row.get(k)) for k in RESULT_COLUMNS]
        )
    return out.getvalue()


def render_results_xlsx(run_meta: dict, rows: list[dict]) -> bytes:
    """Two-sheet workbook: Summary (run metadata as key/value) + Results
    (one row per test query)."""
    import io

    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font

    def _cell(value: Any) -> Any:
        v = _flatten_cell(value)
        if isinstance(v, dict):
            import json
            v = json.dumps(v, default=str)
        if isinstance(v, str):
            # Control characters (which can appear in raw LLM output) make
            # openpyxl raise IllegalCharacterError — strip them.
            return ILLEGAL_CHARACTERS_RE.sub("", v)
        return v

    wb = Workbook()
    bold = Font(bold=True)

    summary = wb.active
    summary.title = "Summary"
    summary.append(["field", "value"])
    for c in summary[1]:
        c.font = bold
    for key, value in run_meta.items():
        summary.append([key, _cell(value)])
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 60

    results = wb.create_sheet("Results")
    results.append(RESULT_COLUMNS)
    for c in results[1]:
        c.font = bold
    for row in rows:
        results.append([_cell(row.get(k)) for k in RESULT_COLUMNS])
    results.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
