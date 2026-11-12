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
REGULATIONS = Path(__file__).resolve().parents[1] / "seeds" / "knowledge_bases" / "content"
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


@pytest.mark.parametrize("path", SEEDS, ids=lambda p: p.stem)
def test_every_seed_ships_an_answer_keyed_example(path):
    inputs = json.loads(path.read_text())["items"][0]["validation_inputs"]
    assert inputs and all(i["type"] == "text" and i["text"] and "Answer key" in i["label"] for i in inputs)
    assert all(i["text"].startswith("FICTIONAL QA MATERIAL") for i in inputs)
    assert len({i["id"] for i in inputs}) == len(inputs)


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


def _dollars(text):
    return int(text.replace("$", "").replace(",", ""))


def test_the_budget_justification_answer_key_adds_up():
    (example,) = _load("budget_generator")["items"][0]["validation_inputs"]
    lines = dict(line.rsplit(": ", 1) for line in example["text"].splitlines()[2:])
    amounts = {k.split(":")[0].split(",")[0]: _dollars(v) for k, v in lines.items()}
    assert amounts["Senior personnel"] == round(96_000 / 9)
    assert amounts["Other personnel"] == 12 * 2_500
    fringe = [_dollars(v) for k, v in lines.items() if k.startswith("Fringe")]
    assert fringe == [round(0.31 * amounts["Senior personnel"]), round(0.02 * amounts["Other personnel"])]
    assert amounts["Travel"] == 2 * 1_800
    direct = amounts["Senior personnel"] + amounts["Other personnel"] + sum(fringe) + amounts["Travel"] + amounts["Materials and supplies"]
    assert amounts["Total direct costs"] == direct
    indirect = next(_dollars(v) for k, v in lines.items() if k.startswith("Indirect"))
    assert indirect == direct // 2 and amounts["Total costs"] == direct + indirect
    for figure in (direct, indirect, direct + indirect, amounts["Materials and supplies"]):
        assert f"${figure:,}" in example["label"]
    # The one line with no stated basis is the one the key says must be flagged.
    assert "Materials and supplies: $4,500" in example["text"]
    assert "Materials and supplies has no stated basis" in example["label"]


def test_the_risk_answer_key_rests_on_terms_the_award_states():
    seed = _load("noa_risk_analysis")
    (example,) = seed["items"][0]["validation_inputs"]
    for term in ("20% of total project costs", "10% of total direct costs", "48% of MTDC",
                 "reimbursement payment", "prior audit", "Export Administration Regulations",
                 "30 days after the end of each calendar quarter", "prior written approval", "$180,000", "$600,000"):
        assert term in example["text"], term
    # The domain the key marks Not assessable really is absent from the award.
    assert "Not assessable" in example["label"]
    assert not re.search(r"intellectual property|publication|data sharing|copyright|patent", example["text"], re.I)
    # The workflow names its domains itself; it no longer depends on a file the catalog doesn't ship.
    prompts = " ".join(t["data"]["prompt"] for s in seed["items"][0]["steps"] for t in s["tasks"])
    assert "Risk_Domains.docx" not in prompts and "eleven risk domains" in prompts


def _example(name):
    (example,) = _load(name)["items"][0]["validation_inputs"]
    return example["text"], example["label"]


def _regulation(name):
    return (REGULATIONS / f"{name}.txt").read_text()


def test_the_coi_answer_key_applies_the_bundled_sfi_definition():
    text, key = _example("compliance_coi_review")
    sfi = _regulation("ecfr-title42-part50-subpart-f")
    # The three rules the key applies, as the bundled 42 CFR 50.603 states them.
    assert "when aggregated, exceeds $5,000" in sfi
    assert "holds any equity interest (e.g., stock, stock option, or other ownership interest)" in sfi
    assert "upon receipt of income related to such rights and interests" in sfi
    assert "travel that is reimbursed or sponsored by a Federal, state, or local government agency, an Institution of higher education" in sfi
    assert "privately held; not publicly traded" in text and "4% founder equity" in text
    agrivance = 3_000 + 2_500
    assert "consulting fees of $3,000" in text and "stock valued at $2,500" in text
    assert agrivance > 5_000 and f"${agrivance:,}" in key
    assert "$4,000 honorarium" in text and "No equity is held in Prairie Instruments" in text
    assert 4_000 <= 5_000 and "Prairie Instruments Inc. is NOT one" in key
    assert "No income related to this patent has been received" in text


def test_the_export_answer_key_rests_on_734_8_and_the_document():
    text, key = _example("compliance_export_control")
    ear = _regulation("ecfr-title15-part734")
    # 734.8(b) allows only patent and sponsor-proprietary prepublication review.
    assert "(1) Prepublication review is conducted solely to ensure that publication would not compromise patent rights" in ear
    assert "has reviewed and approved the proposed publication in writing" in text
    assert "fundamental research exclusion is NOT available" in key
    # The unit's classification really is unstated, so the key can't be answered EAR99.
    assert not re.search(r"ECCN|EAR99|\b\d[A-E]\d{3}\b", text)
    assert "none has been determined" in text
    embargo_headings = " ".join(h for h in _regulation("ecfr-title15-part746").splitlines() if h.startswith("§ 746."))
    for country in ("Germany", "India", "Brazil"):
        assert country in text and country not in embargo_headings


def test_the_irb_answer_key_follows_subpart_d():
    text, key = _example("compliance_irb_protocol")
    common_rule = _regulation("ecfr-title45-part46")
    assert "Paragraph (d)(2)(iii) of this section may not be applied to research subject to subpart D" in common_rule
    assert "only may apply to research subject to subpart D involving educational tests or the observation of public behavior" in common_rule
    assert "Exempt, Category 2" in text and "aged 15–17" in text and "All participants are minors" in text
    assert "recorded interview" in text and "names are recorded" in text
    assert "120 high school students" in text and "120 participants" in key
    assert "Data security plan: To be determined." in text
    assert not re.search(r"parent|guardian|assent", text, re.I)


def _budget_lines(text):
    rows = {}
    for line in text.splitlines():
        m = re.match(r"([A-Z][a-z ]+): \$([\d,]+) / \$([\d,]+)$", line)
        if m:
            rows[m.group(1)] = (_dollars(m.group(2)), _dollars(m.group(3)))
    return rows


def test_the_reconciliation_answer_key_matches_the_statement():
    text, key = _example("financial_budget_reconciliation")
    rows = _budget_lines(text)
    direct = [k for k in rows if k not in ("Indirect costs", "Total")]
    for col in (0, 1):
        direct_total = sum(rows[k][col] for k in direct)
        assert rows["Indirect costs"][col] == round(direct_total * 0.40)
        assert rows["Total"][col] == direct_total + rows["Indirect costs"][col]
    budget, actual = rows["Total"]
    assert f"Remaining balance: ${budget - actual:,}" in text
    flagged = set()
    for name in direct:
        b, a = rows[name]
        if b == 0:
            continue
        variance, pct = a - b, (a - b) / b * 100
        sign = "+" if variance > 0 else "−"
        assert f"{sign}${abs(variance):,} ({sign}{abs(pct):.1f}%)" in key, name
        if abs(pct) > 25:
            flagged.add(name)
    assert flagged == {"Travel", "Supplies"}
    assert f"{actual / budget:.1%}" in key and f"${budget - actual:,}" in key
    # The award's own rebudgeting threshold, and the over-budget movement under it.
    assert "exceeds 10% of the total budget for the budget period" in text
    moved = sum(max(rows[k][1] - rows[k][0], 0) for k in direct)
    assert moved < budget * 0.10 and f"${budget // 10:,}" in key


def test_the_cost_allocation_answer_key_adds_up():
    text, key = _example("financial_cost_allocation")
    uniform = _regulation("ecfr-title2-part200-subpart-e")
    assert "The cost of alcoholic beverages is unallowable." in uniform
    assert "Costs of entertainment, including amusement, diversion, and social activities" in uniform
    assert "the cost must be allocated to the projects based on the proportional benefit" in uniform
    assert "Direct charging of these costs may be appropriate only if they meet all of the following conditions" in uniform
    assert "$650, including $180 for wine" in text and "$3,000, charged 100% to this award" in text
    assert "three projects, each using it equally" in text
    overcharge = 3_000 - 3_000 // 3
    assert f"${3_000 // 3:,} is allocable" in key and f"${overcharge:,} is overcharged" in key
    assert f"${650 + overcharge + 4_000:,}" in key
    assert "integral" not in text


def test_the_progress_report_answer_key_matches_the_report():
    text, key = _example("post_award_progress_report")
    assert "Aim 3: Develop a predictive model" in text
    accomplishments = text.split("Accomplishments", 1)[1].split("Problems encountered", 1)[0]
    assert "Aim 3" not in accomplishments, "the key says Aim 3 has no reported progress"
    spent, budget = 98_000, 150_000
    assert f"${spent:,} of the ${budget:,} year 1 budget" in text
    assert f"({spent / budget:.1%})" in key and f"${budget - spent:,} ({(budget - spent) / budget:.1%})" in key
    assert "In preparation." in text


def test_the_subaward_answer_key_values_are_verbatim():
    text, key = _example("subaward_extraction")
    for value in ("EXA-2027-4410", "SUB-2027-018", "$148,250.00", "$450,000.00", "52% of modified total direct costs",
                  "Example Coastal Institute", "Coastal Drone Survey Methods", "Example Science Agency"):
        assert value in text and value.replace("52% of modified total direct costs", "52% of MTDC") in key
    assert "[ ] Equipment inventory report" in text
    assert "[X] Annual technical report" in text and "[X] Final invention report" in text
    assert not re.search(r"carry.?forward", text, re.I)
    financial = next(c for c in text.splitlines() if c.startswith("Financial Contact:"))
    assert not re.search(r"\(\d{3}\)", financial)
