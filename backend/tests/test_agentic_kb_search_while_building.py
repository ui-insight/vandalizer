"""Chat's agent searches a knowledge base that is refreshing a source.

#1036: a refresh keeps a source's indexed chunks until the new text replaces
them, so a KB reads "building" while it answers in full, and the KB panel lets
chat in when the KB has chunks. The agent's search_knowledge_base still
refused anything not "ready", so a scheduled refresh of one page took the
whole KB out of agentic chat until it finished.
"""

from unittest.mock import patch

import pytest

import tests.test_agentic_kb_page_hedging as hedging
from tests.test_agentic_kb_page_hedging import _passages, _result, _search


_ready_kb = hedging._kb


def _kb_with(status: str, total_chunks: int):
    def make():
        kb = _ready_kb()
        kb.status, kb.total_chunks = status, total_chunks
        return kb
    return make


@pytest.mark.asyncio
async def test_a_building_kb_with_indexed_text_is_searched():
    with patch.object(hedging, "_kb", _kb_with("building", 208)):
        out, _ = await _search([_result("Subrecipient monitoring is required.", page=4)])
    assert _passages(out), out
    assert not any("error" in e for e in out)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,chunks", [("building", 0), ("empty", 0), ("unavailable", 12)])
async def test_a_kb_with_nothing_searchable_still_says_so(status, chunks):
    with patch.object(hedging, "_kb", _kb_with(status, chunks)):
        out, _ = await _search([_result("Subrecipient monitoring is required.", page=4)])
    assert out[0]["error"].startswith("Knowledge base")
    assert status in out[0]["error"]
