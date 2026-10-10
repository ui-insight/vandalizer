"""The Budget Analyzer's arithmetic is computed in code, not by the model (#1013 §4).

The seed's cross-field rules run on the extracted budget inside the workflow
(ExtractionNode), and the analysis prompt receives the results as a labeled
section. The budgets below were worked by hand; the expected figures are in
the comments so they can be checked independently of the code.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.cross_field_rules import validate_rule_shape
from app.services.workflow_engine import (
    RULE_CHECKS_LABEL,
    ExtractionNode,
    MultiTaskNode,
    _build_combined_context,
    describe_rule_checks,
    evaluate_rule_checks,
)

SEED = Path(__file__).resolve().parents[1] / "seeds" / "workflows" / "pre_award_budget_analyzer.json"


def _seed_rules() -> list[dict]:
    data = json.loads(SEED.read_text())
    return data["items"][0]["steps"][0]["tasks"][0]["data"]["cross_field_rules"]


# Senior 120,000 + Other personnel 60,000 + Fringe 54,000 + Equipment 25,000
# + Domestic travel 8,000 + Participant support 20,000 + Materials 12,000
# + Subcontracts 40,000 + Other direct 6,000 = 345,000 total direct.
# MTDC base = 345,000 - 25,000 equipment - 20,000 participant support = 300,000
# (the one subaward, 40,000, is under its first 50,000, so all of it stays in).
# 50% of 300,000 = 150,000 indirect; 345,000 + 150,000 = 495,000 total.
CORRECT = {
    "Senior Personnel Costs": "$120,000",
    "Other Personnel Costs": "$60,000",
    "Fringe Benefits": "$54,000",
    "Equipment": "$25,000",
    "Travel Domestic": "$8,000",
    "Travel Foreign": "N/A",
    "Participant Support Costs": "$20,000",
    "Materials and Supplies": "$12,000",
    "Subcontracts": "$40,000",
    "Consultant Costs": None,
    "Other Direct Costs": "$6,000",
    "Total Direct Costs": "$345K",
    "Indirect Cost Rate": "50%",
    "Indirect Cost Base": "$300,000",
    "Indirect Costs": "$150,000",
    "Total Project Cost": "$0.495 million",
}


def _statuses(entity: dict) -> dict[str, str]:
    (block,) = evaluate_rule_checks(_seed_rules(), [entity])
    return {r["label"]: r["status"] for r in block["results"]}


def _result(entity: dict, label_start: str) -> dict:
    (block,) = evaluate_rule_checks(_seed_rules(), [entity])
    return next(r for r in block["results"] if r["label"].startswith(label_start))


def test_the_seed_rules_are_well_formed_and_use_extracted_fields():
    data = json.loads(SEED.read_text())
    fields = {f.strip() for f in data["items"][0]["steps"][0]["tasks"][0]["data"]["searchphrases"].split(",")}
    rules = _seed_rules()
    assert len({r["id"] for r in rules}) == len(rules)
    for rule in rules:
        ok, error = validate_rule_shape(rule)
        assert ok, error
        named = [rule.get(k) for k in ("target_field", "base_field", "rate_field", "field", "minuend_field")]
        named += rule.get("source_fields", []) + rule.get("subtrahend_fields", [])
        assert {n for n in named if n} <= fields, rule["id"]


def test_a_correct_budget_passes_every_check():
    assert set(_statuses(CORRECT).values()) == {"pass"}
    direct = _result(CORRECT, "Direct cost categories")
    assert direct["computed"] == "345000"
    # Categories the budget doesn't state are named, not silently zeroed.
    assert direct["assumed_zero"] == ["Travel Foreign", "Consultant Costs"]
    assert _result(CORRECT, "Indirect Costs equal")["computed"] == "150000"


def test_a_planted_total_error_fails_only_the_total():
    # 345,000 + 150,000 = 495,000, not 500,000.
    statuses = _statuses({**CORRECT, "Total Project Cost": "$500,000"})
    assert statuses["Total Direct Costs plus Indirect Costs equal Total Project Cost"] == "fail"
    assert list(statuses.values()).count("fail") == 1
    assert "difference 5000" in _result({**CORRECT, "Total Project Cost": "$500,000"}, "Total Direct")["message"]


def test_a_rate_applied_wrongly_fails_the_rate_check():
    # 165,000 is 55% of 300,000; the stated rate is 50% (150,000).
    entity = {**CORRECT, "Indirect Costs": "$165,000", "Total Project Cost": "$510,000"}
    statuses = _statuses(entity)
    assert statuses["Indirect Costs equal the Indirect Cost Rate applied to the Indirect Cost Base"] == "fail"
    assert list(statuses.values()).count("fail") == 1
    assert "difference 15000" in _result(entity, "Indirect Costs equal")["message"]


def test_a_base_that_includes_equipment_fails_the_exclusion_check():
    # Base = full 345,000 (equipment and participant support left in):
    # 50% of it is 172,500, so the rate check itself is consistent, but the
    # base exceeds 345,000 - 25,000 - 20,000 = 300,000 by 45,000.
    entity = {**CORRECT, "Indirect Cost Base": "$345,000", "Indirect Costs": "$172,500",
              "Total Project Cost": "$517,500"}
    statuses = _statuses(entity)
    assert statuses["Indirect Cost Base leaves out equipment and participant support costs"] == "fail"
    assert statuses["Indirect Costs equal the Indirect Cost Rate applied to the Indirect Cost Base"] == "pass"
    assert "exceeds the bound by 45000" in _result(entity, "Indirect Cost Base")["message"]


def test_a_passing_base_check_does_not_claim_the_base_is_right():
    message = _result(CORRECT, "Indirect Cost Base")["message"]
    assert "does not confirm" in message


def test_a_missing_input_is_not_checked_rather_than_guessed():
    entity = {**CORRECT, "Indirect Cost Rate": None}
    statuses = _statuses(entity)
    assert statuses["Indirect Costs equal the Indirect Cost Rate applied to the Indirect Cost Base"] == "unparseable"
    # A missing total isn't a zero: the total check can't be made either.
    assert _statuses({**CORRECT, "Total Project Cost": "TBD"})[
        "Total Direct Costs plus Indirect Costs equal Total Project Cost"] == "unparseable"


def test_a_rate_range_is_not_checked():
    entity = {**CORRECT, "Indirect Cost Rate": "48-52%"}
    result = _result(entity, "Indirect Costs equal")
    assert result["status"] == "unparseable"
    assert "range" in result["message"]


def test_a_bare_rate_is_read_as_a_percentage_and_says_so():
    result = _result({**CORRECT, "Indirect Cost Rate": "50"}, "Indirect Costs equal")
    assert result["status"] == "pass"
    assert "read as 50%" in result["message"]


def test_conflicting_documents_are_checked_separately():
    # The award states 52% but carries the proposal's 150,000 indirect:
    # 52% of 300,000 is 156,000.
    award = {**CORRECT, "Indirect Cost Rate": "52%"}
    blocks = evaluate_rule_checks(_seed_rules(), [CORRECT, award])
    rate = [next(r for r in b["results"] if r["rule_type"] == "product_equals") for b in blocks]
    assert [r["status"] for r in rate] == ["pass", "fail"]
    text = describe_rule_checks(blocks)
    assert "Extracted record 1:" in text and "Extracted record 2:" in text


def test_disabled_rules_and_no_rules_produce_no_checks():
    rules = [{**r, "enabled": False} for r in _seed_rules()]
    assert evaluate_rule_checks(rules, [CORRECT]) == []
    assert evaluate_rule_checks(None, [CORRECT]) == []


# --- the workflow carries the checks to the analysis prompt -----------------

@patch("app.services.workflow_engine.data_extraction_model")
def test_the_extraction_step_attaches_the_checks(mock_extract):
    mock_extract.return_value = {"raw": [dict(CORRECT)], "formatted": "…"}
    node = ExtractionNode({"searchphrases": list(CORRECT), "cross_field_rules": _seed_rules()})
    out = node.process({"output": ["doc-1"], "step_name": "Document"})
    (block,) = out["rule_checks"]
    assert {r["status"] for r in block["results"]} == {"pass"}
    # The extracted record itself is unchanged.
    assert out["output"] == [CORRECT]


@patch("app.services.workflow_engine.data_extraction_model")
def test_an_extraction_without_rules_keeps_its_output_shape(mock_extract):
    mock_extract.return_value = {"raw": [dict(CORRECT)], "formatted": "…"}
    out = ExtractionNode({"searchphrases": list(CORRECT)}).process({"output": ["doc-1"], "step_name": "Document"})
    assert "rule_checks" not in out


def test_a_multi_task_step_carries_the_checks():
    checks = [{"entity": 0, "results": [{"label": "x", "status": "pass", "message": "ok"}]}]
    extraction = SimpleNamespace(
        process=lambda inputs: {"output": [CORRECT], "rule_checks": checks},
        _apply_post_process=lambda r: r, has_side_effects=lambda: False,
    )
    kb = SimpleNamespace(
        process=lambda inputs: {"output": "2 CFR 200.1 passages"},
        _apply_post_process=lambda r: r, has_side_effects=lambda: False,
    )
    step = MultiTaskNode("Extract Budget Fields")
    step.add_tasks([extraction, kb])
    assert step.process({})["rule_checks"] == checks


def test_the_prompt_context_includes_the_checks():
    checks = evaluate_rule_checks(_seed_rules(), [{**CORRECT, "Total Project Cost": "$500,000"}])
    context = _build_combined_context({}, {"output": [CORRECT], "rule_checks": checks}, ["step_input"])
    assert f"=== {RULE_CHECKS_LABEL} ===" in context
    assert "- FAIL — Total Direct Costs plus Indirect Costs equal Total Project Cost" in context
    assert "do not supply the arithmetic yourself" in context
    # Without checks the context is the raw payload, as before.
    assert _build_combined_context({}, {"output": [CORRECT]}, ["step_input"]) == [CORRECT]


# --- the seeder gives existing installs the rules ---------------------------

def _installed(rules, *, owner="system"):
    ss = SimpleNamespace(cross_field_rules=rules, save=AsyncMock())
    task = SimpleNamespace(name="Extraction", data={"search_set_uuid": "ss-1"})
    step = SimpleNamespace(name="Extract Budget Fields", tasks=["t1"])
    wf = SimpleNamespace(user_id=owner, steps=["s1"])
    return wf, step, task, ss


async def _patch_rules(wf, step, task, ss):
    from scripts import seed_catalog

    item = json.loads(SEED.read_text())["items"][0]
    with patch.object(seed_catalog.WorkflowStep, "get", AsyncMock(return_value=step)), \
         patch.object(seed_catalog.WorkflowStepTask, "get", AsyncMock(return_value=task)), \
         patch.object(seed_catalog.SearchSet, "find_one", AsyncMock(return_value=ss)):
        return await seed_catalog._patch_catalog_rules(wf, item)


@pytest.mark.asyncio
async def test_an_existing_install_gains_the_rules():
    wf, step, task, ss = _installed([])
    assert await _patch_rules(wf, step, task, ss) == 4
    assert [r["id"] for r in ss.cross_field_rules] == [r["id"] for r in _seed_rules()]
    ss.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_rule_an_admin_disabled_stays_disabled():
    disabled = {**_seed_rules()[0], "enabled": False}
    wf, step, task, ss = _installed([disabled])
    assert await _patch_rules(wf, step, task, ss) == 3
    assert ss.cross_field_rules[0] == disabled


@pytest.mark.asyncio
async def test_a_users_copy_is_left_alone():
    wf, step, task, ss = _installed([], owner="user-1")
    assert await _patch_rules(wf, step, task, ss) == 0
    ss.save.assert_not_awaited()
