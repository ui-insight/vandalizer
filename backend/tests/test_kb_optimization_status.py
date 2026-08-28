"""The "Optimized" badge: what it means and when it goes stale."""

import datetime
from types import SimpleNamespace

from app.services.kb_optimization_status import (
    QueryStamp,
    SourceStamp,
    compute_optimization_status,
)

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC)      # run started
T_APPLY = T0 + datetime.timedelta(hours=1)
BEFORE = T0 - datetime.timedelta(days=1)
AFTER = T0 + datetime.timedelta(days=2)


def _run(*, uuid="run-1", snapshot=None, best_config=None, started_at=T0):
    return SimpleNamespace(
        uuid=uuid,
        started_at=started_at,
        completed_at=T_APPLY,
        best_config=best_config if best_config is not None else {"k": 8},
        test_query_snapshot=snapshot,
    )


def _snapshot(query_uuids, answers=None, total_sources=10):
    import hashlib
    answers = answers or {}
    return {
        "total": len(query_uuids),
        "query_uuids": list(query_uuids),
        "expected_answer_hashes": {
            u: hashlib.sha256(a.encode()).hexdigest()[:16] for u, a in answers.items()
        },
        "total_sources": total_sources,
    }


def _sources(n_before, n_after=0):
    return (
        [SourceStamp(f"s{i}", BEFORE) for i in range(n_before)]
        + [SourceStamp(f"n{i}", AFTER) for i in range(n_after)]
    )


def _queries(uuids, answers=None, created=BEFORE, updated=None):
    answers = answers or {}
    return [QueryStamp(u, created, updated, answers.get(u)) for u in uuids]


def _status(**kw):
    base = dict(
        rag_config_override={"k": 8, "model": "m"},
        override_set_at=T_APPLY,
        override_run_uuid="run-1",
        applied_run=None,
        latest_completed_run=None,
        sources=[],
        queries=[],
    )
    base.update(kw)
    return compute_optimization_status(**base)


# --- nothing to say ----------------------------------------------------------

def test_no_override_and_no_completed_run_is_none():
    assert _status(rag_config_override=None, override_set_at=None, override_run_uuid=None) is None


def test_empty_override_dict_is_not_optimized():
    assert _status(rag_config_override={}, override_set_at=None, override_run_uuid=None) is None


# --- available: tuned but not applied ----------------------------------------

def test_completed_run_with_settings_but_no_override_is_available():
    st = _status(
        rag_config_override=None, override_set_at=None, override_run_uuid=None,
        latest_completed_run=_run(uuid="run-9"),
    )
    assert st.state == "available"
    assert st.last_run_uuid == "run-9"
    assert st.last_run_at == T_APPLY
    assert st.applied_at is None


def test_completed_run_without_best_config_is_not_available():
    st = _status(
        rag_config_override=None, override_set_at=None, override_run_uuid=None,
        latest_completed_run=_run(best_config={}),
    )
    assert st is None


# --- applied, fresh ----------------------------------------------------------

def test_applied_with_unchanged_corpus_and_eval_set_is_fresh():
    q = ["q1", "q2", "q3", "q4", "q5"]
    answers = {u: f"answer {u}" for u in q}
    run = _run(snapshot=_snapshot(q, answers, total_sources=10))
    st = _status(
        applied_run=run, latest_completed_run=run,
        sources=_sources(10), queries=_queries(q, answers),
    )
    assert st.state == "applied"
    assert st.stale is False
    assert st.stale_reasons == []
    assert st.tuned_keys == ["k", "model"]
    assert st.applied_at == T_APPLY
    assert st.applied_run_uuid == "run-1"
    assert (st.sources_at_run, st.sources_added, st.sources_removed) == (10, 0, 0)
    assert (st.queries_at_run, st.queries_added, st.queries_removed, st.queries_edited) == (5, 0, 0, 0)


def test_small_change_below_the_fraction_stays_fresh():
    q = [f"q{i}" for i in range(20)]
    run = _run(snapshot=_snapshot(q, total_sources=50))
    st = _status(
        applied_run=run, latest_completed_run=run,
        sources=_sources(50, n_after=4),          # 4/50 = 8% < 10%
        queries=_queries(q + ["new1"]),           # 1/20 = 5%
    )
    assert st.state == "applied"
    assert st.sources_added == 4
    assert st.queries_added == 1


# --- stale: sources -----------------------------------------------------------

def test_adding_a_tenth_of_the_sources_is_stale():
    q = ["q1", "q2"]
    run = _run(snapshot=_snapshot(q, total_sources=50))
    st = _status(applied_run=run, latest_completed_run=run,
                 sources=_sources(50, n_after=5), queries=_queries(q))
    assert st.state == "stale"
    assert st.stale is True
    assert st.stale_reasons == [
        "Sources changed since the settings were tuned: 5 added (had 50 sources).",
    ]


def test_removing_sources_is_detected_from_the_snapshot_total():
    q = ["q1", "q2"]
    run = _run(snapshot=_snapshot(q, total_sources=10))
    st = _status(applied_run=run, latest_completed_run=run,
                 sources=_sources(8), queries=_queries(q))   # two of the ten are gone
    assert st.state == "stale"
    assert st.sources_removed == 2
    assert "2 removed (had 10 sources)" in st.stale_reasons[0]


def test_one_change_on_a_three_source_kb_is_material():
    q = ["q1"]
    run = _run(snapshot=_snapshot(q, total_sources=3))
    st = _status(applied_run=run, latest_completed_run=run,
                 sources=_sources(3, n_after=1), queries=_queries(q))
    assert st.state == "stale"


# --- stale: eval set -----------------------------------------------------------

def test_eval_set_churn_is_stale_and_says_what_moved():
    q = [f"q{i}" for i in range(10)]
    answers = {u: f"answer {u}" for u in q}
    run = _run(snapshot=_snapshot(q, answers, total_sources=10))
    now_answers = dict(answers, q0="rewritten")             # 1 edited
    current = [u for u in q if u != "q9"] + ["q-new"]        # 1 removed, 1 added
    st = _status(applied_run=run, latest_completed_run=run,
                 sources=_sources(10), queries=_queries(current, now_answers))
    assert st.state == "stale"
    assert (st.queries_added, st.queries_removed, st.queries_edited) == (1, 1, 1)
    assert st.stale_reasons == [
        "Test questions changed since the settings were tuned: 1 added, 1 removed, "
        "1 expected answer edited (had 10 questions).",
    ]


def test_an_edit_falls_back_to_updated_at_when_the_snapshot_has_no_hash():
    q = ["q1", "q2"]
    run = _run(snapshot=_snapshot(q, answers={}, total_sources=10))   # no hashes recorded
    st = _status(
        applied_run=run, latest_completed_run=run, sources=_sources(10),
        queries=[QueryStamp("q1", BEFORE, AFTER, None), QueryStamp("q2", BEFORE, None, None)],
    )
    assert st.queries_edited == 1
    assert st.state == "stale"   # 1/2 = 50%


# --- overrides that predate the run link ----------------------------------------

def test_override_without_a_run_uses_apply_time_and_creation_stamps():
    st = _status(
        override_run_uuid=None, applied_run=None,
        sources=_sources(9) + [SourceStamp("late", T_APPLY + datetime.timedelta(days=1))],
        queries=_queries(["q1", "q2"]),
    )
    assert st.state == "stale"           # 1 added of 9 present at apply = 11%
    assert st.sources_at_run == 9
    assert st.sources_added == 1
    assert st.sources_removed == 0       # undetectable without a snapshot; never guessed


def test_naive_datetimes_from_mongo_are_treated_as_utc():
    naive_before = BEFORE.replace(tzinfo=None)
    st = _status(
        override_set_at=T_APPLY.replace(tzinfo=None),
        applied_run=None, override_run_uuid=None,
        sources=[SourceStamp("s1", naive_before)],
        queries=[QueryStamp("q1", naive_before, None, None)],
    )
    assert st.state == "applied"
    assert st.applied_at.tzinfo is not None


def test_both_reasons_are_reported_together():
    q = ["q1", "q2"]
    run = _run(snapshot=_snapshot(q, total_sources=2))
    st = _status(applied_run=run, latest_completed_run=run,
                 sources=_sources(2, n_after=2), queries=_queries(q + ["q3", "q4"]))
    assert st.state == "stale"
    assert len(st.stale_reasons) == 2
