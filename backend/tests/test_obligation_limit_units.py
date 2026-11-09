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


async def test_rate_against_rate_is_added_within_the_limit():
    clean, reason = await _check(_limit(22.5, RATE_QUOTE))
    assert reason is None
    assert clean["unit"] == "%"
    assert (clean["observed_value"], clean["limit_value"]) == (22.5, 22.5)


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
