"""Running a validation over a user-selected subset of test queries.

Support ticket: Validation › Test Queries offered only "Delete selected";
evaluators want to smoke-test a few questions and export just those from
History. A subset run is a measurement of a hand-picked few, so it must never
stand in for the full eval set as the KB's quality score.
"""

import datetime
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.validation_run import SMOKE_TEST_SOURCE
from app.services import kb_validation_service


SNAPSHOT = {"recorded": True, "fingerprint": "f00", "total_sources": 1, "total_chunks": 4, "sources": []}


def _tq(uuid: str) -> MagicMock:
    tq = MagicMock()
    tq.uuid, tq.query, tq.expected_answer, tq.category = uuid, f"Q {uuid}?", "A", None
    return tq


async def _run(query_uuids, all_uuids=("q1", "q2", "q3")):
    """run_kb_validation with everything it touches stubbed. Returns
    (result, persist kwargs, the queries the judge saw)."""
    fake_kb = MagicMock()
    fake_kb.uuid, fake_kb.title, fake_kb.rag_config_override = "kb-1", "KB", None
    find = MagicMock()
    find.to_list = AsyncMock(return_value=[_tq(u) for u in all_uuids])
    persisted: dict = {}

    async def fake_persist(**kw):
        persisted.update(kw)
        vr = MagicMock()
        vr.score, vr.score_breakdown = 50.0, {}
        return vr

    judge = AsyncMock(return_value={
        "details": [{"query_uuid": u, "judge": {"score": 1.0, "verdict": "PASS"}} for u in all_uuids],
        "avg_judge_score": 1.0, "num_queries_judged": 1,
    })

    async def fake_precision(kb_uuid, tqs):
        return {"total_queries": len(tqs), "avg_precision": 1.0, "details": [{"query": t.query} for t in tqs]}

    with ExitStack() as stack:
        KB = stack.enter_context(patch.object(kb_validation_service, "KnowledgeBase"))
        TQ = stack.enter_context(patch.object(kb_validation_service, "KBTestQuery"))
        stack.enter_context(patch.object(
            kb_validation_service, "check_source_health",
            AsyncMock(return_value={"ratio": 1.0, "total": 1, "details": []}),
        ))
        stack.enter_context(patch.object(
            kb_validation_service, "check_chunk_coverage", AsyncMock(return_value={"ratio": 1.0}),
        ))
        stack.enter_context(patch(
            "app.services.kb_source_snapshot.snapshot_kb_sources", AsyncMock(return_value=SNAPSHOT),
        ))
        stack.enter_context(patch.object(
            kb_validation_service, "check_retrieval_precision", AsyncMock(side_effect=fake_precision),
        ))
        stack.enter_context(patch(
            "app.services.config_service.get_user_model_name", AsyncMock(return_value="m"),
        ))
        stack.enter_context(patch.object(kb_validation_service, "judge_test_queries", judge))
        VR = stack.enter_context(patch("app.models.validation_run.ValidationRun"))
        stack.enter_context(patch(
            "app.services.quality_service.persist_validation_run", AsyncMock(side_effect=fake_persist),
        ))
        stack.enter_context(patch("app.services.quality_service.compute_quality_tier", return_value="A"))
        SC = stack.enter_context(patch("app.models.system_config.SystemConfig"))
        KB.find_one = AsyncMock(return_value=fake_kb)
        TQ.find = MagicMock(return_value=find)
        VR.find_one = AsyncMock(return_value=MagicMock())
        SC.get_config = AsyncMock(return_value=MagicMock())
        result = await kb_validation_service.run_kb_validation(
            "kb-1", "u1", mode="judge", query_uuids=query_uuids,
        )
    judged = judge.call_args.args[1]
    return result, persisted, judged


@pytest.mark.asyncio
async def test_selected_queries_run_alone_and_persist_as_a_smoke_test():
    result, persisted, judged = await _run(["q3", "q1", "nope"])

    assert sorted(t.uuid for t in judged) == ["q1", "q3"]
    assert result["num_test_queries"] == 2
    # ``selected`` is what ran, ``requested`` what was asked for — the two
    # differ here because "nope" is not a query of this KB (the route refuses
    # such a selection up front; the service still records both counts).
    assert result["query_selection"] == {"selected": 2, "requested": 3, "total": 3}
    # Tagged, so nothing that reads "the latest run" as the KB's quality
    # picks it up — and History can label it.
    assert persisted["source"] == SMOKE_TEST_SOURCE


@pytest.mark.asyncio
async def test_a_full_run_is_untagged_and_records_no_selection():
    result, persisted, judged = await _run(None)

    assert len(judged) == 3
    assert result["query_selection"] is None
    assert persisted["source"] is None
    # The KB as the run found it is part of the persisted result.
    assert result["kb_sources"] is SNAPSHOT
    assert persisted["result"]["kb_sources"] is SNAPSHOT


@pytest.mark.asyncio
async def test_no_matching_query_is_an_error_not_an_empty_run():
    with pytest.raises(ValueError, match="selected test queries"):
        await _run(["nope"])


# ---------------------------------------------------------------------------
# A smoke test never becomes the item's quality score
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_smoke_test_run_skips_quality_metadata():
    from app.services.quality_service import persist_validation_run

    with (
        patch("app.services.quality_service.ValidationRun") as MockVR,
        patch("app.services.quality_service.update_quality_metadata", new_callable=AsyncMock) as uqm,
    ):
        vr = MagicMock()
        vr.insert = AsyncMock()
        MockVR.return_value = vr
        result = {"raw_score": 90.0, "num_test_queries": 2, "num_sources": 1, "sources": [], "num_runs": 1}

        await persist_validation_run(
            "knowledge_base", "kb-1", "KB", "kb_validation", result, "u1", source=SMOKE_TEST_SOURCE,
        )
        vr.insert.assert_awaited_once()
        assert MockVR.call_args.kwargs["source"] == SMOKE_TEST_SOURCE
        uqm.assert_not_awaited()

        await persist_validation_run(
            "knowledge_base", "kb-1", "KB", "kb_validation", result, "u1",
        )
        assert MockVR.call_args.kwargs["source"] is None
        uqm.assert_awaited_once()


def test_latest_run_reads_leave_smoke_tests_out():
    """Both "latest run" readers filter on the same clause — the one that
    sets VerifiedItemMetadata and the one regression detection compares to."""
    import inspect
    from app.services import quality_service

    assert quality_service.NOT_SMOKE_TEST == {"source": {"$ne": SMOKE_TEST_SOURCE}}
    for fn in (quality_service._get_latest_run, quality_service.get_latest_validation):
        assert "NOT_SMOKE_TEST" in inspect.getsource(fn), fn.__name__


def test_admin_aggregate_reads_leave_smoke_tests_out():
    """The dashboard's trend arrows, per-model averages, fleet timeline and
    summary are built from every run they read — a three-query smoke test
    scoring 100 must not flip a trend or enter an average. (History keeps
    them: it labels the row "selected n/N".)"""
    import inspect
    from app.services import quality_service

    for fn in (
        quality_service.get_quality_summary,
        quality_service.get_quality_timeline,
        quality_service.get_quality_by_model,
        quality_service.get_quality_items,
        quality_service.get_quality_item_detail,
    ):
        assert "NOT_SMOKE_TEST" in inspect.getsource(fn), fn.__name__


# ---------------------------------------------------------------------------
# The export says what the run covered
# ---------------------------------------------------------------------------


def test_export_run_meta_carries_the_selection():
    from app.services.kb_validation_export import build_kb_validation_results_export

    kb = SimpleNamespace(uuid="kb-1", title="KB", tags=[], total_sources=1, total_chunks=1,
                         resource_config=None, rag_config_override=None)
    vr = SimpleNamespace(
        uuid="run-1", score=70.0, score_breakdown={},
        created_at=datetime.datetime(2026, 9, 9, tzinfo=datetime.timezone.utc),
        result_snapshot={
            "mode": "judge", "judge_model": "m", "raw_score": 70.0, "num_test_queries": 2,
            "query_selection": {"selected": 2, "total": 150},
            "retrieval_precision": {"details": [
                {"query": "Q q1?", "query_uuid": "q1", "actual_answer": "A", "judge": {"score": 1.0}},
                {"query": "Q q3?", "query_uuid": "q3", "actual_answer": "B", "judge": {"score": 0.0}},
            ]},
        },
    )
    payload, run_meta, rows = build_kb_validation_results_export(
        kb=kb, vr=vr, test_queries=[], catalog_version=None,
        exported_by_user_id="u", exported_at="2026-09-09T00:00:00+00:00",
    )
    assert run_meta["query_selection"] == {"selected": 2, "total": 150}
    assert [r["query_uuid"] for r in rows] == ["q1", "q3"]
    assert payload["validation_run"]["query_selection"]["selected"] == 2
