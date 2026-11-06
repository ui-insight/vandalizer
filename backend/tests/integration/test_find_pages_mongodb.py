"""Chat finds a saved Page by its name, against real MongoDB aggregation.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_find_pages_mongodb.py

Support ticket: "Update the page 'NIH R01 Budget Dashboard — 5-Year
Breakdown'" searched documents, the library and page templates, found
nothing, and ended in a generic error. Chat had no way to look up Pages.
"""
import os
from uuid import uuid4

import pytest
from pymongo import MongoClient

from app.services import artifacts
from app.services.chat_artifact_tools import _find_pages

pytestmark = [
    pytest.mark.integration_tier2,
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
]

TITLE = "NIH R01 Budget Dashboard - 5-Year Breakdown"


@pytest.fixture
def db():
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    name = f"find_pages_{uuid4().hex[:8]}"
    yield client[name]
    client.drop_database(name)
    client.close()


def _page(db, owner, title, key, team=None, versions=1):
    doc = artifacts.create(db, owner, title, f"<main><h1>{title}</h1></main>", key, {"kind": "chat"})
    for n in range(2, versions + 1):
        doc = artifacts.revise(db, doc, title, f"<main><h1>{title}</h1><p>v{n}</p></main>", doc["latest_revision"])
    if team:
        doc = artifacts.share_team(db, doc, team)
    return doc


def test_finds_a_page_by_name_whatever_dash_or_quotes_the_request_uses(db):
    mine = _page(db, "ra", TITLE, "a", versions=6)
    _page(db, "ra", "NSF Budget Summary", "b")
    _page(db, "someone-else", "NIH R01 Budget Dashboard - private copy", "c")
    found = _find_pages(db, "ra", [], "‘NIH R01 Budget Dashboard — 5-Year Breakdown’", 10)
    assert [p["title"] for p in found["items"]] == [TITLE]
    page = found["items"][0]
    assert page["artifact_uuid"] == mine["uuid"] and page["version"] == 6 and page["yours"] is True
    assert page["link"] == f"/pages/{mine['uuid']}"


def test_team_pages_are_found_but_not_marked_yours_and_others_stay_private(db):
    _page(db, "colleague", "Team Award Tracker", "t", team="team-1")
    _page(db, "colleague", "Private Award Tracker", "p")
    found = _find_pages(db, "ra", ["team-1"], "award tracker", 10)
    assert [(p["title"], p["yours"], p["shared_with_team"]) for p in found["items"]] == [("Team Award Tracker", False, True)]


def test_no_name_lists_recent_pages_and_deleted_ones_are_gone(db):
    for i in range(3):
        _page(db, "ra", f"Page {i}", f"k{i}")
    gone = _page(db, "ra", "Deleted page", "gone")
    db.html_artifacts.update_one({"uuid": gone["uuid"]}, {"$set": {"deleted_at": gone["created_at"]}})
    found = _find_pages(db, "ra", [], "", 2)
    assert len(found["items"]) == 2 and found["total"] == 3
    assert _find_pages(db, "ra", [], "Deleted page", 10)["items"] == []
    # Punctuation is ignored, so a regex-looking name can't widen the match.
    assert _find_pages(db, "ra", [], "Page (.*)", 10)["total"] == 3
    assert _find_pages(db, "ra", [], ".*", 10)["total"] == 3  # no words: the recent list, not a regex
