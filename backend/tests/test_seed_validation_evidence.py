"""Catalog workflows ship validation evidence, not an author's rating (#1013 §5).

Every workflow seed carries a validation plan that tests correctness and
omissions, and no seed asserts a quality tier without a measured score. The
example inputs' answer keys are checked against the example documents here,
so a key can't drift from the text it describes.
"""

import datetime
import json
import re
from pathlib import Path

import pytest

from app.services.workflow_engine import evaluate_rule_checks

WORKFLOWS = Path(__file__).resolve().parents[1] / "seeds" / "workflows"
SEEDS = sorted(WORKFLOWS.glob("*.json"))
VALID_CATEGORIES = {"completeness", "formatting", "content", "accuracy"}


def _load(name):
    return json.loads((WORKFLOWS / f"{name}.json").read_text())


@pytest.mark.parametrize("path", SEEDS, ids=lambda p: p.stem)
def test_every_seed_has_a_substantive_validation_plan(path):
    plan = json.loads(path.read_text())["items"][0]["validation_plan"]
    assert len(plan) >= 3
    assert {c["category"] for c in plan} <= VALID_CATEGORIES
    # Formatting checks alone don't establish correctness.
    assert any(c["category"] == "accuracy" for c in plan)
    assert any(c["category"] in ("completeness", "content") for c in plan)
    assert len({c["id"] for c in plan}) == len(plan)


@pytest.mark.parametrize("path", SEEDS, ids=lambda p: p.stem)
def test_no_seed_asserts_a_tier_it_did_not_measure(path):
    meta = json.loads(path.read_text())["_seed_meta"]
    if meta.get("quality_score") is None:
        assert "quality_tier" not in meta
        assert "quality_grade" not in meta


def test_the_priority_workflows_ship_example_inputs():
    for name in ("pre_award_budget_analyzer", "rfa_checklist", "foa_checklist",
                 "pre_award_compliance_checker", "noa_summary", "award_compliance_analysis"):
        inputs = _load(name)["items"][0]["validation_inputs"]
        assert inputs and all(i["type"] == "text" and i["text"] and "Answer key" in i["label"] for i in inputs), name


def test_the_budget_answer_key_matches_the_budget():
    seed = _load("pre_award_budget_analyzer")
    (example,) = seed["items"][0]["validation_inputs"]
    fields = dict(
        re.match(r"([^:]+):\s*(.+?)(?:\s*\(.*\))?$", line).groups()
        for line in example["text"].splitlines()[2:] if ":" in line
    )
    rules = seed["items"][0]["steps"][0]["tasks"][0]["data"]["cross_field_rules"]
    (block,) = evaluate_rule_checks(rules, [fields])
    statuses = {r["rule_type"] + ":" + r["label"][:20]: r["status"] for r in block["results"]}
    assert sorted(statuses.values()) == ["fail", "pass", "pass", "pass"]
    total = next(r for r in block["results"] if r["label"].startswith("Total Direct Costs plus"))
    assert total["status"] == "fail" and "difference 5000" in total["message"]
    assert "overstated by $5,000" in example["label"]


def test_the_award_answer_key_dates_follow_from_the_award():
    (example,) = _load("noa_summary")["items"][0]["validation_inputs"]
    period_end, project_end = datetime.date(2028, 6, 30), datetime.date(2029, 6, 30)
    assert "through June 30, 2028" in example["text"] and "through June 30, 2029" in example["text"]
    assert "90 days after the end of each budget period" in example["text"]
    assert f"{period_end + datetime.timedelta(90):%B %-d, %Y}" in example["label"]
    assert f"{project_end + datetime.timedelta(120):%B %-d, %Y}" in example["label"]
    assert f"{project_end - datetime.timedelta(10):%B %-d, %Y}" in example["label"]


def test_the_solicitation_answer_key_uses_the_amended_deadline():
    (example,) = _load("rfa_checklist")["items"][0]["validation_inputs"]
    assert "The new sponsor deadline is November 19, 2026 at 5:00 p.m. Pacific Time." in example["text"]
    assert "sponsor deadline November 19, 2026, 5:00 p.m. Pacific Time (amended from November 12)" in example["label"]
