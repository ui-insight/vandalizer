"""check_compliance must not report clearance it didn't establish (#1013 §1).

Runs the real CrossFieldValidator; only the extraction-set lookup and the
extraction itself are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SUM_RULE = {
    "id": "r1", "type": "sum_equals", "enabled": True,
    "source_fields": ["Direct", "Indirect"], "target_field": "Total",
}
DATE_RULE = {
    "id": "r2", "type": "date_order", "enabled": True,
    "field_a": "Start", "field_b": "End",
}


def _ctx():
    ctx = MagicMock()
    ctx.deps.team_id = "team1"
    ctx.deps.user_id = "user1"
    ctx.deps.active_document_uuids = []
    return ctx


def _verified(*fields):
    return {f: {"quote": "q", "page": 1, "verified": True} for f in fields}


async def _check(rules, extraction, doc_uuids=("doc-1",)):
    from app.services.chat_tools import check_compliance

    ss = MagicMock()
    ss.verified = True
    ss.title = "Budget Rules"
    ss.normalized_cross_field_rules = MagicMock(return_value=rules)
    with patch("app.services.chat_tools.SearchSet") as MockSS, \
         patch("app.services.chat_tools._resolve_doc_uuids", side_effect=lambda c, d: d), \
         patch("app.services.chat_tools._execute_extraction",
               new_callable=AsyncMock, return_value=extraction):
        MockSS.find_one = AsyncMock(return_value=ss)
        return await check_compliance(_ctx(), "ss-1", list(doc_uuids))


@pytest.mark.asyncio
async def test_all_unparseable_is_not_compliant():
    # The issue's reproduction: Direct "TBD" used to return all_compliant=True
    # with 0 checks passed.
    result = await _check([SUM_RULE], {
        "entities": [{"Direct": "TBD", "Indirect": "$100", "Total": "$1100"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect", "Total")],
    })
    assert result["all_compliant"] is None
    assert result["outcome"] == "inconclusive"
    doc = result["results"][0]
    assert doc["compliant"] is None
    assert doc["outcome"] == "inconclusive"
    assert doc["checks_unparseable"] == 1
    assert "TBD" in doc["inconclusive"][0]["message"]
    assert "Do NOT say" in result["note_inconclusive"]


@pytest.mark.asyncio
async def test_mixed_pass_and_unparseable_is_inconclusive():
    result = await _check([SUM_RULE, DATE_RULE], {
        "entities": [{"Direct": "$1,000", "Indirect": "$100", "Total": "$1,100",
                      "Start": "Q1", "End": "2027-01-01"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect", "Total", "Start", "End")],
    })
    assert result["outcome"] == "inconclusive"
    assert result["results"][0]["checks_passed"] == 1
    assert result["results"][0]["compliant"] is None


@pytest.mark.asyncio
async def test_no_entities_is_not_clearance():
    result = await _check([SUM_RULE], {"entities": [], "documents": [], "sources": []})
    assert result["documents_checked"] == 0
    assert result["all_compliant"] is None


@pytest.mark.asyncio
async def test_every_rule_passing_on_traced_values_is_compliant():
    result = await _check([SUM_RULE], {
        "entities": [{"Direct": "$1.2 million", "Indirect": "$300,000", "Total": "$1,500,000"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect", "Total")],
    })
    assert result["outcome"] == "pass"
    assert result["all_compliant"] is True
    assert result["results"][0]["compliant"] is True
    assert "not a review of every sponsor" in result["scope"]


@pytest.mark.asyncio
async def test_pass_on_untraced_value_is_inconclusive():
    result = await _check([SUM_RULE], {
        "entities": [{"Direct": "$1,000", "Indirect": "$100", "Total": "$1,100"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect")],
        "source_note": "1 extracted value(s) have no verified source passage.",
    })
    doc = result["results"][0]
    assert doc["outcome"] == "inconclusive"
    assert "Total" in doc["inconclusive"][0]["message"]
    assert result["source_note"].startswith("1 extracted value")


@pytest.mark.asyncio
async def test_partially_unreadable_batch_is_not_compliant():
    note = ("1 document(s) were NOT extracted because their text is "
            "unavailable: Scan.pdf (text extraction FAILED).")
    result = await _check([SUM_RULE], {
        "entities": [{"Direct": "$1,000", "Indirect": "$100", "Total": "$1,100"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect", "Total")],
        "note": note,
    }, doc_uuids=("doc-1", "doc-2"))
    assert result["results"][0]["outcome"] == "pass"
    assert result["outcome"] == "inconclusive"
    assert result["all_compliant"] is None
    assert result["documents_requested"] == 2
    assert result["note"] == note


@pytest.mark.asyncio
async def test_a_failure_still_reports_fail():
    result = await _check([SUM_RULE, DATE_RULE], {
        "entities": [{"Direct": "$1,000", "Indirect": "$100", "Total": "$1,200",
                      "Start": "TBD", "End": "2027-01-01"}],
        "documents": ["Budget.pdf"],
        "sources": [_verified("Direct", "Indirect", "Total")],
    })
    assert result["outcome"] == "fail"
    assert result["all_compliant"] is False
    assert result["total_violations"] == 1
