import json

import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.services.chat_budget_tables import reconcile_budget_tables
from tests.test_chat_output import chat_harness as chat_harness


VALUES = {
    "Salaries": [50000, 52000],
    "Fringe": [15000, 15600],
    "Travel": [5000, 4400],
    "Supplies": [10000, 8000],
    "F&A": [41600, 41600],
    "Total": [121600, 121600],
}
ENTITY = {f"Budget {category} Year {year}": amount
          for category, amounts in VALUES.items() for year, amount in enumerate(amounts, 1)}
OMITTED = """## Budget by year

| Category | Year 1 | Year 2 |
| --- | ---: | ---: |
| Travel | $5,000 | $4,400 |
| Supplies | $10,000 | $8,000 |
| F&A | $41,600 | $41,600 |
| **Total** | **$121,600** | **$121,600** |
"""


def results(*entities, tool_name="run_pin_on_project"):
    return [{"tool_name": tool_name, "content": {
        "extraction_set": "NIH R01 Extraction", "entities": list(entities),
    }}]


@pytest.mark.parametrize("tool_name", ["run_pin_on_project", "run_extraction"])
def test_restores_all_categories_and_both_years_reconcile(tool_name):
    output = reconcile_budget_tables(OMITTED, results(ENTITY, tool_name=tool_name))
    for category, amounts in VALUES.items():
        assert f"| {category} | ${amounts[0]:,} | ${amounts[1]:,} |" in output
    assert "do not reconcile" not in output
    # Test the displayed table, not just the source fixture's arithmetic.
    rows = [line.split("|")[1:-1] for line in output.splitlines() if line.startswith("|")][2:]
    for col in (1, 2):
        displayed = [int(row[col].strip().replace("$", "").replace(",", "")) for row in rows]
        assert sum(displayed[:-1]) == displayed[-1] == 121600


@pytest.mark.parametrize("entity", [
    {"Budget": {category: {f"Year {year}": amount for year, amount in enumerate(amounts, 1)}
                for category, amounts in VALUES.items()}},
    {"Budget": json.dumps({f"Year {year}": {category: amounts[year - 1] for category, amounts in VALUES.items()}
                           for year in (1, 2)})},
    {key.replace(" ", "_"): value for key, value in ENTITY.items()},
    {"Budget": [{"Category": category, "Year 1": amounts[0], "Year 2": amounts[1]}
                for category, amounts in VALUES.items()]},
    {"Budget": [{"Year": year, **{category: amounts[year - 1] for category, amounts in VALUES.items()}}
                for year in (1, 2)]},
])
def test_nested_or_json_budget_values_are_not_lost(entity):
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "| Salaries | $50,000 | $52,000 |" in output
    assert "| Fringe | $15,000 | $15,600 |" in output


def test_preserves_zero_and_custom_categories_without_a_category_allowlist():
    entity = {**ENTITY, "Budget Sequencing Services Year 1": 0, "Budget Sequencing Services Year 2": 0}
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "| Sequencing Services | $0 | $0 |" in output


def test_aliases_do_not_duplicate_salaries_fringe_or_indirect_costs():
    entity = {key.replace("Salaries", "Salaries and Wages").replace("Fringe", "Fringe Benefits")
              .replace("F&A", "Indirect Costs"): value for key, value in ENTITY.items()}
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "| Salaries and Wages | $50,000 | $52,000 |" in output
    assert output.count("$41,600") == 2
    assert "do not reconcile" not in output


def test_subtotals_and_rates_are_not_added_twice():
    entity = {**ENTITY, "Budget Total Direct Costs Year 1": 80000, "Budget Total Direct Costs Year 2": 80000,
              "Budget F&A Rate Year 1": 52, "Budget F&A Rate Year 2": 52,
              "Budget MTDC Base Year 1": 80000, "Budget MTDC Base Year 2": 80000,
              "Participants Year 1": 10, "Participants Year 2": 12}
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "subtotal; not added again" in output
    assert "do not reconcile" not in output
    assert "Rate" not in output and "Base" not in output and "Participants" not in output


def test_missing_amount_stays_unknown_instead_of_becoming_zero():
    entity = {**ENTITY, "Budget Salaries Year 2": None}
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "| Salaries | $50,000 | Not found |" in output
    assert "| Reported total | $121,600 | $121,600 |" in output
    assert "Missing amounts are not treated as zero" in output


def test_source_discrepancy_is_not_hidden_by_changing_the_total():
    entity = {**ENTITY, "Budget Total Year 2": 122600}
    output = reconcile_budget_tables(OMITTED, results(entity))
    assert "| Reported total | $121,600 | $122,600 |" in output
    assert "do not reconcile" in output
    assert "balancing" not in output


def test_unavailable_or_ambiguous_evidence_does_not_invent_missing_categories():
    for evidence in ([], results(ENTITY, {**ENTITY, "Budget Salaries Year 1": 60000})):
        output = reconcile_budget_tables(OMITTED, evidence)
        assert "Salaries" not in output
        assert "do not reconcile" in output


def test_other_documents_and_non_extraction_tools_are_not_used_as_evidence():
    other = {key: value * 2 for key, value in ENTITY.items()}
    for evidence in (results(other), results(ENTITY, tool_name="search_documents")):
        assert "Salaries" not in reconcile_budget_tables(OMITTED, evidence)


def test_nonbudget_table_and_reconciled_table_are_unchanged():
    ordinary = "| Task | Owner |\n| --- | --- |\n| Review | Jane |\n"
    assert reconcile_budget_tables(ordinary, results(ENTITY)) == ordinary
    counts = "| Cohort | Year 1 |\n| --- | --- |\n| New | 20 |\n| Total | 100 |\n"
    assert reconcile_budget_tables(counts, results(ENTITY)) == counts
    complete = reconcile_budget_tables(OMITTED, results(ENTITY))
    assert reconcile_budget_tables(complete, results(ENTITY)) == complete


def test_cent_precision_and_negative_adjustments():
    table = "| Category | Year 1 |\n| --- | --- |\n| Travel | $0.10 |\n| Supplies | $0.20 |\n| Refund | ($0.05) |\n| Total | $0.25 |\n"
    assert reconcile_budget_tables(table, []) == table


async def test_project_extraction_repairs_the_stream_and_saved_reply_once(chat_harness):
    calls = []

    async def execute(confirmed: bool):
        calls.append(confirmed)
        return results(ENTITY)[0]["content"]

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaToolCall(name="run_pin_on_project", json_args='{"confirmed":true}')}
        else:
            for char in OMITTED:
                yield char

    agent = Agent(FunctionModel(stream_function=respond), tools=[Tool(execute, name="run_pin_on_project")])
    chunks = await chat_harness.run(agent)
    assert calls == [True]
    assert not [c for c in chunks if c["kind"] == "error"]
    text = "".join(c["content"] for c in chunks if c["kind"] == "text")
    assert "| Salaries | $50,000 | $52,000 |" in text
    assert "| Fringe | $15,000 | $15,600 |" in text
    saved = chat_harness.finalize.call_args
    assert saved.args[1] == text
    assert saved.kwargs["segments"][-1]["content"] == text
    assert not saved.kwargs["unsupported_figures"]
