"""Public Page links end to end: expiry, sign-in audience, view record, reminders.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_public_page_links_mongodb.py

Real MongoDB because view counts and version-link settings are $inc /
arrayFilters updates the in-memory fakes can't run.
"""
import datetime
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.services import artifacts, public_page_access
from app.services.access_control import TeamAccessContext
from tests.test_chat_routes import _auth, _make_user

pytestmark = [
    pytest.mark.integration_tier2,
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio,
]

NOW = datetime.datetime.now(datetime.timezone.utc)


@pytest.fixture
def db():
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    name = f"public_links_{uuid4().hex[:8]}"
    yield client[name]
    client.drop_database(name)
    client.close()


@pytest.fixture
async def env(db):
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app
        owner = _make_user("owner")
        app.dependency_overrides[get_current_user] = lambda: owner
        app.dependency_overrides[get_settings] = lambda: Settings(artifact_public_sharing_enabled=True)
        viewer = {"user": None}

        async def optional_user(request, settings):
            return viewer["user"]

        with patch("app.routers.artifacts.get_sync_db", return_value=db), \
             patch("app.routers.artifacts.access_control.get_team_access_context", AsyncMock(return_value=TeamAccessContext())), \
             patch("app.routers.artifacts.optional_user", optional_user):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                cookies, headers = _auth("owner")
                client.cookies.update(cookies)
                yield SimpleNamespace(client=client, headers=headers, viewer=viewer, db=db)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_settings, None)


def _page(db):
    return artifacts.create(db, "owner", "NIH R01 Budget Dashboard", "<main><h1>Budget</h1><p>$1,250,000</p></main>", uuid4().hex, {"kind": "chat"})


def _person(email="ra@uidaho.edu", verified=True, user_id="ra"):
    return SimpleNamespace(user_id=user_id, email=email, email_verified=verified, name="Reviewing RA")


async def test_sign_in_link_counts_views_and_names_viewers(env):
    page = _page(env.db)
    expires = (NOW + datetime.timedelta(days=30)).isoformat()
    published = await env.client.put(f"/api/pages/{page['uuid']}/publication", headers=env.headers, json={
        "revision": page["latest_revision"], "expires_at": expires, "audience": "signed_in", "emails": ["RA@uidaho.edu"]})
    assert published.status_code == 200, published.text
    token = published.json()["public_token"]
    url = f"/api/pages/public/{token}"

    env.viewer["user"] = None
    assert (await env.client.get(url)).status_code == 401
    assert (await env.client.get(f"{url}/content")).status_code == 401  # the HTML too
    env.viewer["user"] = _person(email="someone@else.edu", user_id="x")
    assert (await env.client.get(url)).status_code == 403
    env.viewer["user"] = _person()
    first = await env.client.get(url)
    assert first.status_code == 200 and first.json()["expires_at"].startswith(expires[:10])
    await env.client.get(url)
    assert (await env.client.get(f"{url}/content")).status_code == 200

    detail = (await env.client.get(f"/api/pages/{page['uuid']}", headers=env.headers)).json()
    main = detail["public_links"]["main"]
    assert main["audience"] == "signed_in" and main["emails"] == ["ra@uidaho.edu"] and not main["expired"]
    assert main["views"]["count"] == 2 and main["views"]["last_at"]
    assert [(v["email"], v["count"]) for v in main["viewers"]] == [("ra@uidaho.edu", 2)]


async def test_expired_link_says_so_until_extended_and_anyone_links_stay_anonymous(env):
    page = _page(env.db)
    published = (await env.client.put(f"/api/pages/{page['uuid']}/publication", headers=env.headers,
                                      json={"revision": page["latest_revision"]})).json()
    token = published["public_token"]
    env.db.html_artifacts.update_one({"uuid": page["uuid"]}, {"$set": {"public_expires_at": NOW - datetime.timedelta(minutes=1)}})
    expired = await env.client.get(f"/api/pages/public/{token}")
    assert expired.status_code == 410 and "expired" in expired.json()["detail"]
    assert (await env.client.get(f"/api/pages/public/{token}/content")).status_code == 410

    extended = await env.client.put(f"/api/pages/{page['uuid']}/publication/settings", headers=env.headers,
                                    json={"expires_at": (NOW + datetime.timedelta(days=7)).isoformat(), "audience": "anyone"})
    assert extended.status_code == 200
    env.viewer["user"] = _person()  # signed in, but the link is for anyone
    assert (await env.client.get(f"/api/pages/public/{token}")).status_code == 200
    main = (await env.client.get(f"/api/pages/{page['uuid']}", headers=env.headers)).json()["public_links"]["main"]
    assert main["views"]["count"] == 1 and main["viewers"] == []

    # Removing the link clears its settings; a later link starts fresh.
    await env.client.delete(f"/api/pages/{page['uuid']}/publication", headers=env.headers)
    stored = env.db.html_artifacts.find_one({"uuid": page["uuid"]})
    assert "public_expires_at" not in stored and "public_views" not in stored


async def test_version_links_have_their_own_settings_and_the_owner_sees_every_live_link(env):
    page = _page(env.db)
    rev1 = page["latest_revision"]
    page = artifacts.revise(env.db, page, "NIH R01 Budget Dashboard", "<main><p>$1,255,000</p></main>", rev1)
    await env.client.put(f"/api/pages/{page['uuid']}/publication", headers=env.headers, json={"revision": page["latest_revision"]})
    separate = await env.client.put(f"/api/pages/{page['uuid']}/publication", headers=env.headers, json={
        "revision": rev1, "separate_link": True, "expires_at": (NOW + datetime.timedelta(days=2)).isoformat()})
    token = next(p["token"] for p in separate.json()["publications"] if p["revision"] == rev1)
    assert (await env.client.get(f"/api/pages/public/{token}")).status_code == 200
    links = (await env.client.get("/api/pages/public-links", headers=env.headers)).json()["links"]
    assert [(link["kind"], link["version"]) for link in links] == [("version", 1), ("main", 2)]  # soonest expiry first
    assert links[0]["views"]["count"] == 1 and links[1]["expires_at"] is None

    # Two days out: one reminder for the version link, never twice.
    with patch("app.services.notification_service.create_notification_sync") as bell:
        assert public_page_access.remind_expiring(env.db) == 1
        assert public_page_access.remind_expiring(env.db) == 0
    kwargs = bell.call_args.kwargs
    assert kwargs["user_id"] == "owner" and kwargs["kind"] == "page_link_expiring" and kwargs["link"].endswith("#share")


async def test_bad_settings_are_refused(env):
    page = _page(env.db)
    response = await env.client.put(f"/api/pages/{page['uuid']}/publication", headers=env.headers, json={
        "revision": page["latest_revision"], "audience": "anyone", "emails": ["a@b.edu"]})
    assert response.status_code == 422
    assert env.db.html_artifacts.find_one({"uuid": page["uuid"]})["public_token"] is None  # nothing published
    missing = await env.client.put(f"/api/pages/{page['uuid']}/publication/settings", headers=env.headers, json={"audience": "anyone"})
    assert missing.status_code == 404
