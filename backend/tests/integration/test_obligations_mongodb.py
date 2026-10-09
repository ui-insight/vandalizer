"""The RA inbox against real MongoDB (#999).

Uses the fictional sponsor notice, amendment and proposal draft from
tests/fixtures/ra_usability_sources as project documents with page markers,
and checks what the inbox accepts, rejects, replaces and shows.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_obligations_mongodb.py
"""

import os
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.routers import obligations as obligations_router
from app.services import obligation_service

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "ra_usability_sources"


def _paged(pages):
    raw, markers = "", []
    for i, page in enumerate(pages, 1):
        markers.append({"kind": "page", "value": i, "char_offset": len(raw)})
        raw += page.strip() + "\n"
    return raw, markers


async def _setup():
    owner = User(user_id="ra-owner", email="owner@example.test", name="RA Owner")
    viewer = User(user_id="pi-viewer", email="pi@example.test", name="PI")
    await owner.insert()
    await viewer.insert()
    await SmartFolder(uuid="proj-root", parent_id="0", title="Resilience Pilot", user_id="ra-owner").insert()
    project = Project(uuid="proj-1", title="Community Resilience Pilot", owner_user_id="ra-owner", root_folder_uuid="proj-root")
    await project.insert()
    await ProjectMembership(project_uuid="proj-1", user_id="pi-viewer", role="viewer").insert()

    notice = (SRC / "sponsor-notice.txt").read_text()
    parts = re.split(r"\n(?=\d\. )", notice.strip())
    proposal = (SRC / "proposal-draft.txt").read_text()
    head, rest = proposal.split("\nDraft budget", 1)
    budget, notes = rest.split("\nReadiness notes", 1)
    for uuid, title, pages in [
        ("notice", "sponsor-notice.pdf", [parts[0] + "\n" + parts[1]] + parts[2:]),
        ("amend", "sponsor-amendment.pdf", [(SRC / "sponsor-amendment.txt").read_text()]),
        ("prop", "proposal-draft.pdf", [head, "Draft budget" + budget, "Readiness notes" + notes]),
    ]:
        raw, markers = _paged(pages)
        await SmartDocument(
            uuid=uuid, title=title, raw_text=raw, text_markers=markers, path=f"x/{uuid}.pdf",
            downloadpath=f"x/{uuid}.pdf", user_id="ra-owner", folder="proj-root",
        ).insert()
    return owner, viewer, project


def _deadline(title, deadline_type, due, doc, page, quote):
    return {"kind": "deadline", "title": title, "deadline_type": deadline_type, "due_at": due,
            "sources": [{"document_uuid": doc, "page": page, "quote": quote}]}


ORIGINAL = _deadline("Sponsor deadline", "sponsor_submission", "2026-11-12T17:00", "notice", 2,
                     "The sponsor deadline is November 12, 2026 at 5:00 p.m. Pacific Time.")
AMENDED = _deadline("Sponsor deadline (amended)", "sponsor_submission", "2026-11-19T17:00", "amend", 1,
                    "The new sponsor deadline is November 19, 2026 at 5:00 p.m. Pacific Time.")
INTERNAL = _deadline("Institutional review deadline", "internal_routing", "2026-11-09T12:00", "notice", 2,
                     "The institutional review deadline is November 9, 2026 at noon Pacific Time.")
CAP = {"kind": "limit", "title": "Direct-cost cap", "limit_value": 180000, "observed_value": 200000, "unit": "$",
       "sources": [
           {"document_uuid": "notice", "page": 3, "quote": "The maximum direct-cost request is $180,000.", "role": "limit"},
           {"document_uuid": "prop", "page": 2, "quote": "Direct-cost total: $200,000", "role": "observed"},
       ]}
LETTER = {"kind": "required_material", "title": "Signed community-partner letter",
          "sources": [{"document_uuid": "prop", "page": 3, "quote": "A partner has promised a letter,\nbut a signed letter has not been received."}]}


async def test_checked_items_are_saved_and_an_amendment_replaces_the_original(mongo_client):
    owner, _viewer, project = await _setup()
    first = await obligation_service.propose(project, owner, [ORIGINAL, INTERNAL, CAP, LETTER])
    assert first["rejected"] == []
    for a in first["accepted"]:
        await obligation_service.save_checked(project, owner, a["clean"])

    second = await obligation_service.propose(project, owner, [AMENDED])
    (accepted,) = second["accepted"]
    assert accepted["replaces"]["due_at"].startswith("2026-11-12")
    new = await obligation_service.save_checked(project, owner, accepted["clean"])

    inbox = await obligation_service.inbox(owner)
    assert [i["title"] for i in inbox] == [
        "Institutional review deadline", "Sponsor deadline (amended)", "Direct-cost cap", "Signed community-partner letter",
    ]
    assert inbox[1]["supersedes"] and inbox[2]["in_conflict"] is True
    every = await obligation_service.project_obligations(project, owner)
    old = next(i for i in every if i["title"] == "Sponsor deadline")
    assert old["status"] == "superseded" and old["superseded_by"] == new.uuid


@pytest.mark.parametrize("item,reason", [
    ({**AMENDED, "due_at": "2026-11-20"}, "does not state November 20"),
    ({**ORIGINAL, "sources": [{"document_uuid": "notice", "page": 3, "quote": ORIGINAL["sources"][0]["quote"]}]}, "not found on page 3"),
    ({**ORIGINAL, "sources": [{"document_uuid": "notice", "quote": ORIGINAL["sources"][0]["quote"]}]}, "give the page"),
    ({**CAP, "limit_value": 150000}, "does not state the limit value"),
    ({"kind": "required_material", "title": "Page limit", "sources": [{"document_uuid": "notice", "page": 4, "quote": "Budget justifications are limited to 3 pages."}]}, "not found on page 4"),
    ({**LETTER, "sources": [{"document_uuid": "elsewhere", "page": 1, "quote": "x"}]}, "not found or you can't open it"),
])
async def test_items_the_documents_do_not_support_are_rejected_with_the_reason(mongo_client, item, reason):
    owner, _viewer, project = await _setup()
    checked = await obligation_service.propose(project, owner, [item])
    assert checked["accepted"] == []
    assert reason in checked["rejected"][0]["reason"]


async def test_the_same_item_twice_is_not_added_twice(mongo_client):
    owner, _viewer, project = await _setup()
    (a,) = (await obligation_service.propose(project, owner, [LETTER]))["accepted"]
    await obligation_service.save_checked(project, owner, a["clean"])
    again = await obligation_service.propose(project, owner, [LETTER])
    assert again["accepted"] == [] and "already" in again["rejected"][0]["reason"]


async def _client(user):
    app = FastAPI()
    app.include_router(obligations_router.router, prefix="/api/obligations")
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_dismiss_is_personal_done_is_shared_and_viewers_cannot_mark_done(mongo_client):
    owner, viewer, project = await _setup()
    async with await _client(owner) as http:
        created = (await http.post("/api/obligations", json={"project_uuid": "proj-1", "items": [INTERNAL, LETTER]})).json()
        assert len(created["created"]) == 2 and created["rejected"] == []
        letter = next(i for i in created["created"] if i["kind"] == "required_material")
        assert (await http.post(f"/api/obligations/{letter['uuid']}/dismiss", json={"dismissed": True})).status_code == 200
        mine = (await http.get("/api/obligations")).json()["items"]
        assert [i["title"] for i in mine] == ["Institutional review deadline"]
        with_dismissed = (await http.get("/api/obligations", params={"include_dismissed": True})).json()["items"]
        assert any(i["dismissed"] for i in with_dismissed)

    async with await _client(viewer) as http:
        theirs = (await http.get("/api/obligations")).json()["items"]
        assert len(theirs) == 2, "a dismissal on one person's Home doesn't hide it for teammates"
        deadline = next(i for i in theirs if i["kind"] == "deadline")
        assert (await http.post(f"/api/obligations/{deadline['uuid']}/done", json={"done": True})).status_code == 403
        assert (await http.post(f"/api/obligations/{deadline['uuid']}/dismiss", json={"dismissed": True})).status_code == 200

    async with await _client(owner) as http:
        assert (await http.post(f"/api/obligations/{deadline['uuid']}/done", json={"done": True})).status_code == 200
        assert (await http.get("/api/obligations")).json()["items"] == []


async def test_the_inbox_can_be_hidden_for_this_account(mongo_client):
    owner, _viewer, _project = await _setup()
    async with await _client(owner) as http:
        assert (await http.get("/api/obligations")).json()["inbox_hidden"] is False
        assert (await http.put("/api/obligations/home-settings", json={"inbox_hidden": True})).json() == {"inbox_hidden": True}
    assert (await User.find_one(User.user_id == "ra-owner")).home_inbox_hidden is True
