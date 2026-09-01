"""Cross-field rules run on every extraction that has them.

They were reachable only from the Validate tab's button, so a production run
shipped with none of the checks that catch a wrong number applied.
"""

from types import SimpleNamespace

from app.routers.extractions import _evaluate_cross_field_rules

_SUM_RULE = {
    "id": "r1",
    "type": "sum_equals",
    "source_fields": ["Direct Costs", "Indirect Costs"],
    "target_field": "Total Costs",
}


def _search_set(rules):
    return SimpleNamespace(
        uuid="ss-1",
        cross_field_rules=rules,
        normalized_cross_field_rules=lambda: rules,
    )


def test_no_rules_reports_nothing_rather_than_passing():
    assert _evaluate_cross_field_rules(_search_set([]), {"a": "1"}) is None
    assert _evaluate_cross_field_rules(None, {"a": "1"}) is None


def test_budget_that_does_not_add_up_fails():
    report = _evaluate_cross_field_rules(
        _search_set([_SUM_RULE]),
        {"Direct Costs": "$100,000", "Indirect Costs": "$50,000", "Total Costs": "$200,000"},
    )
    assert report["summary"]["fail"] == 1
    assert "difference" in report["results"][0]["message"]


def test_budget_that_adds_up_passes():
    report = _evaluate_cross_field_rules(
        _search_set([_SUM_RULE]),
        {"Direct Costs": "$100,000", "Indirect Costs": "$50,000", "Total Costs": "$150,000"},
    )
    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] == 1


def test_unparseable_is_neither_pass_nor_fail():
    report = _evaluate_cross_field_rules(
        _search_set([_SUM_RULE]),
        {"Direct Costs": "TBD", "Indirect Costs": "$50,000", "Total Costs": "$150,000"},
    )
    assert report["summary"]["unparseable"] == 1
    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] == 0


def test_engine_fault_never_fails_a_run_that_produced_values():
    broken = SimpleNamespace(
        uuid="ss-2",
        cross_field_rules=[_SUM_RULE],
        normalized_cross_field_rules=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert _evaluate_cross_field_rules(broken, {"a": "1"}) is None
