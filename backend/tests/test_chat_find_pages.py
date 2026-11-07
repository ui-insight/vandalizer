"""Chat can find a saved Page by name (support ticket: "Something went wrong")."""
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat_artifact_tools import find_pages, name_pattern


def _context():
    return SimpleNamespace(deps=SimpleNamespace(user=SimpleNamespace(user_id="ra"), user_id="ra"))


def _access():
    return SimpleNamespace(team_uuids={"team-1"}, team_object_ids=set())


@pytest.mark.parametrize("asked, saved, matches", [
    ("NIH R01 Budget Dashboard — 5-Year Breakdown", "NIH R01 Budget Dashboard - 5-Year Breakdown", True),
    ("‘nih r01 budget dashboard’", "NIH R01 Budget Dashboard — 5-Year Breakdown", True),
    ("budget breakdown", "NIH R01 Budget Dashboard — 5-Year Breakdown", True),
    ("NSF dashboard", "NIH R01 Budget Dashboard — 5-Year Breakdown", False),
])
def test_every_word_must_appear_in_any_order(asked, saved, matches):
    assert bool(re.search(name_pattern(asked), saved, re.IGNORECASE | re.DOTALL)) is matches


def test_a_name_without_words_lists_recent_pages():
    assert name_pattern("“ — ”") is None and name_pattern("") is None


@pytest.mark.asyncio
async def test_not_found_says_so_and_points_to_request_changes():
    with patch("app.services.access_control.get_team_access_context", AsyncMock(return_value=_access())), \
         patch("app.services.chat_artifact_tools._call", AsyncMock(return_value={"items": [], "total": 0})) as call:
        out = await find_pages(_context(), "NIH R01 Budget Dashboard", limit=500)
    _fn, user_id, team_ids, name, limit = call.await_args.args
    assert (user_id, team_ids, limit) == ("ra", ["team-1"], 20)
    assert "couldn't find a Page called that" in out["note"] and "Request changes" in out["note"]


@pytest.mark.asyncio
async def test_template_search_failure_is_a_result_not_a_crashed_turn():
    from app.services.chat_page_templates import find_page_templates

    with patch("app.routers.page_templates.browse", AsyncMock(side_effect=RuntimeError("db down"))):
        out = await find_page_templates(_context(), "NIH")
    assert out["items"] == [] and "could not be searched" in out["error"]


def test_the_agent_is_told_pages_are_found_with_find_pages():
    from app.services.chat_tools import TOOLS
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT

    assert find_pages in TOOLS
    assert "call find_pages first" in AGENTIC_CHAT_SYSTEM_PROMPT
