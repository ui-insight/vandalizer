"""Optimizer results read the same in chat as on the tune screen.

Support ticket: an extraction run that scored 93% showed "score 1/100
(was 1)" in chat; its "Best configuration" was the simplest tied setup
(85%) with nothing saying so while the top trial scored 94%; and the
no-settings baseline read 92% in the bars but 91% in the suggestion text.
"""

from types import SimpleNamespace

from app.services.extraction_optimizer import _generate_suggestions
from app.services.optimization_summary import _extraction_winner_details, with_percent_scores


def _trial(trial_id, score, **config):
    return {"trial_id": trial_id, "status": "completed", "score": score, "config": config}


def _run(**extra):
    trials = [
        _trial("t-simple", 0.85, strategy="one-pass", model="gpt-oss-120b"),
        _trial("t-top", 0.94, strategy="two-pass", consensus=True, model="gpt-oss-120b"),
        {"trial_id": "t-failed", "status": "failed", "score": None, "config": {}},
    ]
    base = dict(trials=trials, best_trial_id="t-simple", best_config=trials[0]["config"], baseline_model="gpt-oss-120b")
    return SimpleNamespace(**{**base, **extra})


def test_summary_scores_are_given_as_the_percent_the_screen_shows():
    summary = with_percent_scores({"score": 0.93, "baseline_score": 0.926})
    assert (summary["score_percent"], summary["baseline_score_percent"]) == (93, 93)
    assert with_percent_scores({"score": None, "baseline_score": None})["score_percent"] is None


def test_a_tied_winner_is_told_apart_from_the_top_scoring_trial():
    details = _extraction_winner_details(_run())
    assert details == {
        "best_trial_score_percent": 85,
        "top_trial_score_percent": 94,
        "top_trial_is_best": False,
        "measured_with_model": "gpt-oss-120b",
    }


def test_an_older_run_without_a_winner_id_is_matched_by_its_config():
    details = _extraction_winner_details(_run(best_trial_id=None, baseline_model=None))
    assert details["best_trial_score_percent"] == 85
    assert details["measured_with_model"] is None


def test_suggestions_round_scores_the_way_the_score_bars_do():
    suggestions = _generate_suggestions(
        field_breakdown=[], baseline_no_tool=0.919, baseline_default=0.926, optimized=0.93,
    )
    messages = " ".join(s["message"] for s in suggestions)
    assert "scored 92%" in messages and "91%" not in messages


def test_the_run_endpoint_returns_the_winner_trial_and_model():
    import datetime

    from app.routers.extractions import _serialize_extraction_optimization_run

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    run = SimpleNamespace(
        uuid="r1", search_set_uuid="ss", status="completed", phase="done", progress_message="", current_trial_index=3,
        total_trials_planned=3, best_score_so_far=0.94, best_config_so_far={}, token_budget=1, tokens_used=1,
        estimated_cost_usd=None, actual_cost_usd=None, baseline_no_tool_score=0.92, baseline_default_score=0.93,
        optimized_score=0.85, judge_variance=0.05, judge_model="kimi-k3", best_config={}, trials=[], field_breakdown=[],
        suggestions=[], previous_override=None, options={}, error_message=None, started_at=now, completed_at=now,
        cancel_requested=False, best_trial_id="t-simple", baseline_model="gpt-oss-120b",
    )
    body = _serialize_extraction_optimization_run(run)
    assert (body["best_trial_id"], body["baseline_model"]) == ("t-simple", "gpt-oss-120b")
