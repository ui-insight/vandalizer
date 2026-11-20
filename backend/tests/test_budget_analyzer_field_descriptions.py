"""The Budget Analyzer's field descriptions cover the labels real drafts use (#1057).

In #1005 run 2 the extraction left Total Direct Costs, Total Project Cost and
most categories empty on the fictional proposal draft, because its labels
("Direct-cost total", "Total request", "Subaward") matched no field name, so
no arithmetic rule could run.
"""

import json
from pathlib import Path

import pytest

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "workflows"
DRAFT = Path(__file__).parent / "fixtures" / "ra_usability_sources" / "proposal-draft.txt"


def _extraction():
    data = json.loads((SEEDS / "pre_award_budget_analyzer.json").read_text())
    return data["items"][0]["steps"][0]["tasks"][0]["data"]


def test_every_description_names_a_real_field():
    task = _extraction()
    fields = {k.strip() for k in task["searchphrases"].split(",")}
    assert set(task["field_descriptions"]) <= fields


def test_every_field_a_rule_reads_or_checks_is_described():
    task = _extraction()
    read = set()
    for rule in task["cross_field_rules"]:
        for key in ("source_fields", "subtrahend_fields"):
            read.update(rule.get(key) or [])
        for key in ("target_field", "base_field", "rate_field", "field", "minuend_field"):
            if rule.get(key):
                read.add(rule[key])
    # Participant Support Costs is a sponsor category name used as-is.
    missing = read - set(task["field_descriptions"]) - {"Participant Support Costs", "Equipment"}
    assert not missing, missing


@pytest.mark.parametrize("label,field", [
    ("Personnel", "Senior Personnel Costs"),
    ("Travel", "Travel Domestic"),
    ("Supplies", "Materials and Supplies"),
    ("Subaward", "Subcontracts"),
    ("Direct-cost total", "Total Direct Costs"),
    ("Indirect costs", "Indirect Costs"),
    ("Total request", "Total Project Cost"),
])
def test_the_fixture_drafts_labels_are_covered(label, field):
    assert f"{label}:" in DRAFT.read_text()
    description = _extraction()["field_descriptions"][field]
    assert label.lower() in description.lower() or field.lower().startswith(label.lower())


@pytest.mark.parametrize("field", ["Total Direct Costs", "Total Project Cost"])
def test_stated_totals_are_copied_not_computed(field):
    # A model that sums the lines to fill the total makes the sum rule pass
    # by construction.
    assert "do not add lines up" in _extraction()["field_descriptions"][field]
