"""Questions from a page's viewers to its owner, on MongoDB.

Support ticket: team members and public-link viewers had no way to ask about
a figure or flag a section, and a public page didn't say whose it was.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_page_feedback_mongodb.py
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_settings
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.page_feedback import PageFeedback
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.routers import artifacts as artifacts_router
from app.routers import page_feedback as feedback_router
from app.services import artifacts

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

PAGE = "<h1>NIH R01 Budget</h1><table><tr><td>Equipment</td><td>$20,000</td></tr></table>"
SPOT = {"path": "1/0/0/1", "text": "$20,000"}


@pytest.fixture
def sync_db(sync_mongo):
    with patch("app.tasks.get_sync_db", return_value=sync_mongo), \
         patch("app.routers.artifacts.get_sync_db", return_value=sync_mongo):
        yield sync_mongo


async def _setup(sync_db):
    await Organization(uuid="org", name="University of Idaho Office of Sponsored Programs", org_type="central_office").insert()
    owner = User(user_id="ra", email="ra@example.test", name="Dana Reyes", organization_id="org")
    member = User(user_id="pi", email="pi@example.test", name="Pat Kim")
    outsider = User(user_id="x", email="x@example.test", name="Outsider")
    for u in (owner, member, outsider):
        await u.insert()
    team = Team(uuid="team-1", name="OSP", owner_user_id="ra")
    await team.insert()
    await TeamMembership(team=team.id, user_id="pi", role="member").insert()
    doc = artifacts.create(sync_db, "ra", "NIH R01 Budget", PAGE, "req-1")
    doc = artifacts.revise(sync_db, doc, "NIH R01 Budget", PAGE + "<p>v2</p>", doc["latest_revision"])
    v1, v2 = doc["revisions"][0]["uuid"], doc["revisions"][1]["uuid"]
    artifacts.share_team(sync_db, doc, "team-1", v1)
    doc = artifacts.publish(sync_db, artifacts.get(sync_db, doc["uuid"]), v2) or artifacts.get(sync_db, doc["uuid"])
    doc = artifacts.get(sync_db, doc["uuid"])
    return owner, member, outsider, doc, v1, v2


def _client(user=None):
    app = FastAPI()
    app.include_router(feedback_router.router, prefix="/api/pages")
    app.include_router(artifacts_router.router, prefix="/api/pages")
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: type("S", (), {"artifact_public_sharing_enabled": True})()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_member_asks_owner_answers_and_the_member_hears_back(mongo_client, sync_db):
    owner, member, outsider, doc, v1, v2 = await _setup(sync_db)
    uuid = doc["uuid"]
    async with _client(member) as http:
        listed = (await http.get(f"/api/pages/{uuid}/feedback", params={"revision": v1})).json()
        assert listed["role"] == "member"
        assert listed["shared_by"] == "Shared by Dana Reyes, University of Idaho Office of Sponsored Programs"
        # Only the version shared with the team can be asked about.
        assert (await http.post(f"/api/pages/{uuid}/feedback", json={"revision": v2, "anchor": SPOT, "message": "?"})).status_code == 422
        asked = await http.post(f"/api/pages/{uuid}/feedback", json={
            "revision": v1, "anchor": SPOT, "message": "Is Equipment Y2 $20k the microscope quote?", "kind": "question"})
        assert asked.status_code == 200
        fid = asked.json()["uuid"]
        assert (await http.post(f"/api/pages/{uuid}/feedback", json={"revision": v1, "message": "   "})).status_code == 422

    bell = await Notification.find_one(Notification.user_id == "ra")
    assert bell.kind == "page_feedback" and bell.link == f"/pages/{uuid}?feedback={fid}"
    assert bell.title == "Question on NIH R01 Budget: “$20,000”"
    assert bell.body == "Pat Kim: Is Equipment Y2 $20k the microscope quote?"

    async with _client(outsider) as http:
        assert (await http.post(f"/api/pages/{uuid}/feedback", json={"revision": v1, "message": "hi"})).status_code == 404

    async with _client(member) as http:
        assert (await http.post(f"/api/pages/{uuid}/feedback/{fid}/answer", json={"text": "x"})).status_code == 404

    async with _client(owner) as http:
        mine = (await http.get(f"/api/pages/{uuid}/feedback")).json()
        assert mine["role"] == "owner" and mine["items"][0]["anchor"] == SPOT
        assert (await http.post(f"/api/pages/{uuid}/feedback", json={"revision": v2, "message": "self"})).status_code == 422
        answered = await http.post(f"/api/pages/{uuid}/feedback/{fid}/answer",
                                   json={"text": "Yes — the Zeiss quote, attached in Files.", "on_page": True})
        assert answered.json()["status"] == "answered"

    reply = await Notification.find_one(Notification.user_id == "pi")
    assert reply.kind == "page_feedback_answer" and reply.body == "Dana Reyes: Yes — the Zeiss quote, attached in Files."

    async with _client(member) as http:
        theirs = (await http.get(f"/api/pages/{uuid}/feedback", params={"revision": v1})).json()["items"]
        assert theirs[0]["answer"]["text"].startswith("Yes") and "author_email" not in theirs[0]

    async with _client(owner) as http:
        assert (await http.post(f"/api/pages/{uuid}/feedback/{fid}/status", json={"status": "resolved"})).json()["status"] == "resolved"


async def test_public_questions_only_when_the_owner_allows(mongo_client, sync_db):
    owner, _member, _outsider, doc, _v1, v2 = await _setup(sync_db)
    token = doc["public_token"]
    async with _client() as http:
        info = (await http.get(f"/api/pages/public/{token}/feedback")).json()
        assert info["public_questions"] is False
        assert info["shared_by"] == "Shared by Dana Reyes, University of Idaho Office of Sponsored Programs"
        refused = await http.post(f"/api/pages/public/{token}/feedback", json={"anchor": SPOT, "message": "Why $20k?"})
        assert refused.status_code == 403

    async with _client(owner) as http:
        updated = await http.put(f"/api/pages/{doc['uuid']}/feedback-settings",
                                 json={"public_questions": True, "contact": "OSP, osp@example.edu"})
        assert updated.json()["shared_by"] == "Shared by Dana Reyes, OSP, osp@example.edu"

    with patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)) as email:
        async with _client() as http:
            assert (await http.post(f"/api/pages/public/{token}/feedback", json={
                "anchor": SPOT, "message": "Why $20k in Y2?", "email": "not-an-email"})).status_code == 422
            # A bot filling the hidden field is told "ok" and nothing is kept.
            assert (await http.post(f"/api/pages/public/{token}/feedback", json={
                "anchor": SPOT, "message": "buy now", "website": "spam.example"})).json() == {"ok": True}
            ok = await http.post(f"/api/pages/public/{token}/feedback", json={
                "anchor": SPOT, "message": "Why $20k in Y2?", "name": "Sponsor PO", "email": "po@agency.example"})
            assert ok.json() == {"ok": True}
        items = await PageFeedback.find_all().to_list()
        assert [i.message for i in items] == ["Why $20k in Y2?"] and items[0].revision == v2

        async with _client(owner) as http:
            fid = items[0].uuid
            await http.post(f"/api/pages/{doc['uuid']}/feedback/{fid}/answer", json={"text": "It's the microscope.", "on_page": True})
        sent = email.await_args
        assert sent.args[0] == "po@agency.example"
        assert "It&#x27;s the microscope." in sent.args[2] or "It's the microscope." in sent.args[2]
        assert f"/a/{token}?feedback={fid}" in sent.args[2]

    async with _client() as http:
        shown = (await http.get(f"/api/pages/public/{token}/feedback")).json()["items"]
        assert shown[0]["answer"]["text"] == "It's the microscope."
        assert shown[0]["author_name"] == "A viewer", "a public asker's name isn't published"
        assert "author_email" not in shown[0]
