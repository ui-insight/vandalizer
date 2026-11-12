"""A limit is compared only with a value in the same unit.

Support ticket (vandalizer-dev build 621, NIFA subaward UI-OSU-2026-0412):
the RA inbox showed "Indirect Costs: 17550% exceeds the 22.5% limit". The
limit is 22.5% of TDC (p. 1); the observed value was the $17,550 indirect
cost amount (p. 2), saved with the model's "%" unit.
"""

from types import SimpleNamespace

import pytest

from app.services import obligation_service as svc

LIMIT_QUOTE = "Indirect costs are limited to 22.5% of total direct costs (TDC)."
AMOUNT_QUOTE = "Indirect Costs (22.5% of TDC): $17,550"
RATE_QUOTE = "Indirect cost rate: 22.5% of TDC"


def _limit(observed_value, observed_quote, unit="%"):
    return {
        "kind": "limit", "title": "Indirect Costs", "limit_value": 22.5,
        "observed_value": observed_value, "unit": unit,
        "sources": [
            {"document_uuid": "sub", "page": 1, "quote": LIMIT_QUOTE, "role": "limit"},
            {"document_uuid": "sub", "page": 2, "quote": observed_quote, "role": "observed"},
        ],
    }


@pytest.fixture(autouse=True)
def quotes_verify(monkeypatch):
    async def check_source(raw, user, project):
        return svc.ObligationSource(
            document_uuid=raw["document_uuid"], document_title="Subaward", page=raw["page"],
            quote=raw["quote"], role=raw.get("role") or "evidence",
        ), None

    monkeypatch.setattr(svc, "_check_source", check_source)


async def _check(item):
    return await svc.check_proposal(item, SimpleNamespace(), SimpleNamespace())


@pytest.mark.parametrize("unit", ["%", "$", ""])
async def test_a_percent_limit_against_a_dollar_amount_is_not_added(unit):
    clean, reason = await _check(_limit(17550, AMOUNT_QUOTE, unit))
    assert clean is None
    assert "same unit" in reason
    assert "22.5%" in reason and "$17,550" in reason


async def test_a_limit_restated_as_its_own_observed_value_is_a_plain_limit():
    """Support ticket: "22% against a limit of 22%" and "$9,555 within the
    $9,555 limit". The same figure twice is not a comparison."""
    clean, reason = await _check(_limit(22.5, RATE_QUOTE))
    assert reason is None
    assert clean["unit"] == "%"
    assert (clean["observed_value"], clean["limit_value"]) == (None, 22.5)
    # Nothing is left labelled "Observed value" on a limit with no comparison.
    assert [s.role for s in clean["sources"]] == ["limit", "evidence"]


async def test_a_limit_needs_no_observed_value():
    item = {
        "kind": "limit", "title": "Indirect costs", "limit_value": 9555,
        "sources": [{"document_uuid": "sub", "page": 2, "quote": "Indirect costs shall not exceed $9,555.", "role": "limit"}],
    }
    clean, reason = await _check(item)
    assert reason is None
    assert (clean["observed_value"], clean["limit_value"], clean["unit"]) == (None, 9555, "$")


@pytest.mark.parametrize("clean, line", [
    # Exact value, never rounded to a whole number; "$" before the amount.
    ({"limit_value": 22.5, "observed_value": None, "unit": "%"}, "Cap: 22.5% (Subaward, p. 1)"),
    ({"limit_value": 9555.0, "observed_value": None, "unit": "$"}, "Cap: $9,555 (Subaward, p. 1)"),
    ({"limit_value": 180000.0, "observed_value": 200000.5, "unit": "$"},
     "Cap: $200,000.50 against a limit of $180,000 (Subaward, p. 1)"),
    ({"limit_value": 22.5, "observed_value": 26.0, "unit": "%"}, "Cap: 26% against a limit of 22.5% (Subaward, p. 1)"),
    ({"limit_value": 1200.0, "observed_value": None, "unit": None}, "Cap: 1,200 (Subaward, p. 1)"),
])
def test_the_approval_card_shows_the_figure_that_will_be_saved(clean, line):
    from app.services import chat_tools

    source = svc.ObligationSource(document_uuid="sub", document_title="Subaward", page=1, quote="q", role="limit")
    assert chat_tools._describe_obligation({"kind": "limit", "title": "Cap", "sources": [source], **clean}) == line


async def test_dollar_limit_against_dollar_amount_takes_the_unit_from_the_quotes():
    item = {
        "kind": "limit", "title": "Direct-cost cap", "limit_value": 180000, "observed_value": 200000,
        "unit": "%",  # the model's unit is not trusted
        "sources": [
            {"document_uuid": "n", "page": 3, "quote": "The maximum direct-cost request is $180,000.", "role": "limit"},
            {"document_uuid": "b", "page": 1, "quote": "Total direct costs: $200,000", "role": "observed"},
        ],
    }
    clean, reason = await _check(item)
    assert reason is None
    assert clean["unit"] == "$"


async def test_a_bare_amount_compares_with_a_dollar_limit():
    item = {
        "kind": "limit", "title": "Equipment", "limit_value": 5000, "observed_value": 7200, "unit": "$",
        "sources": [
            {"document_uuid": "n", "page": 1, "quote": "Equipment items over $5,000 need prior approval.", "role": "limit"},
            {"document_uuid": "b", "page": 2, "quote": "Plate reader 7,200", "role": "observed"},
        ],
    }
    clean, reason = await _check(item)
    assert reason is None
    assert clean["unit"] == "$"
