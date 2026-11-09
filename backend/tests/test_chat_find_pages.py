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


# Support ticket: "The latest saved version is Version 8… The published version
# is the same one" while the Page said "Published · version 4" and "The public
# link still shows version 4". find_pages only said "published": true.
def _meta(latest=8, published=4, team=None, owner=True, publications=()):
    revisions = [{"uuid": f"r{n}", "version": n} for n in range(1, latest + 1)]
    return {"revisions": revisions, "latest_revision": f"r{latest}", "can_manage": owner,
            "published_revision": f"r{published}" if published else None,
            "team_id": "team-1" if team else None, "team_revision": f"r{team}" if team else None,
            "publications": [{"revision": f"r{n}"} for n in publications]}


def test_an_older_published_version_is_reported_as_older_than_the_latest():
    from app.services.chat_artifact_tools import version_status

    status = version_status(_meta(latest=8, published=4))
    assert (status["latest_version"], status["published_version"]) == (8, 4)
    assert "public link shows version 4" in status["publication_note"]
    assert "versions 5–8 are not published yet" in status["publication_note"]


@pytest.mark.parametrize("meta, published, note", [
    (_meta(latest=3, published=3), 3, "shows version 3, the latest"),
    (_meta(latest=5, published=4), 4, "version 5 is not published yet"),
    (_meta(latest=2, published=None), None, "Not published"),
    (_meta(latest=6, published=None, publications=(2, 5)), None, "own links: 2, 5"),
])
def test_publication_is_stated_as_it_is(meta, published, note):
    from app.services.chat_artifact_tools import version_status

    status = version_status(meta)
    assert status["published_version"] == published and status["published"] is (published is not None)
    assert note in status["publication_note"]


def test_team_version_is_its_own_pointer():
    from app.services.chat_artifact_tools import version_status

    assert version_status(_meta(latest=8, published=4, team=6))["team_version"] == 6


def test_a_teammate_is_not_told_the_page_is_unpublished():
    from app.services.chat_artifact_tools import version_status

    # A teammate's metadata is narrowed to the shared version only.
    status = version_status({"revisions": [{"uuid": "r6", "version": 6}], "latest_revision": "r6",
                             "can_manage": False, "published_revision": None,
                             "team_id": "team-1", "team_revision": "r6"})
    assert status["team_version"] == 6
    assert "published_version" not in status and "Only the owner" in status["publication_note"]
