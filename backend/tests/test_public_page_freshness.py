"""Public freshness labels describe the visible revision, never private saves."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services import artifacts
from tests.test_artifacts import db as db, make


@pytest.mark.asyncio
@pytest.mark.parametrize("naive_mongo_dates", [False, True])
async def test_logged_out_freshness_tracks_published_revision(client, db, naive_mongo_dates):
    first = make(db)
    second = artifacts.revise(db, first, "Public budget", "<p>Version two</p>", first["latest_revision"])
    published = artifacts.publish(db, second, second["latest_revision"])
    draft = artifacts.revise(db, published, "Private budget", "<p>Secret version three</p>", second["latest_revision"])
    dates = [datetime(2026, 3, day, 15, 30, tzinfo=timezone.utc) for day in (1, 10, 20)]
    for revision, date in zip(draft["revisions"], dates):
        revision["created_at"] = date.replace(tzinfo=None) if naive_mongo_dates else date
    db.html_artifacts.update_one({"uuid": draft["uuid"]}, {"$set": {
        "revisions": draft["revisions"], "updated_at": dates[2],
    }})
    url = f'/api/pages/public/{published["public_token"]}'
    with patch("app.routers.artifacts.get_sync_db", return_value=db):
        response = await client.get(url)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        metadata = response.json()
        assert set(metadata) == {"title", "revision", "version", "updated_at"}
        assert metadata["title"] == "Public budget"
        assert metadata["version"] == 2
        assert metadata["revision"] == second["latest_revision"]
        assert datetime.fromisoformat(metadata["updated_at"].replace("Z", "+00:00")) == dates[1]
        assert "Private budget" not in response.text and "private-chat" not in response.text
        content = await client.get(f'{url}/content', params={"revision": metadata["revision"], "download": "true"})
        assert content.status_code == 200
        assert "attachment" in content.headers["content-disposition"]
        assert "Version two" in content.text and "Secret" not in content.text
        assert (await client.get(f'{url}/content', params={"revision": draft["latest_revision"]})).status_code == 409

        # Publishing again updates both labels; an already-open viewer must not
        # silently load new HTML under its old version/date label.
        artifacts.publish(db, artifacts.get(db, draft["uuid"]), draft["latest_revision"])
        stale = await client.get(f'{url}/content', params={"revision": metadata["revision"]})
        assert stale.status_code == 409
        assert "Reload" in stale.json()["detail"]
        current = (await client.get(url)).json()
        assert current["version"] == 3
        assert current["revision"] == draft["latest_revision"]
        assert datetime.fromisoformat(current["updated_at"].replace("Z", "+00:00")) == dates[2]
        assert (await client.get(f'{url}/content', params={"revision": current["revision"]})).status_code == 200

        artifacts.unpublish(db, artifacts.get(db, draft["uuid"]))
        assert (await client.get(url)).status_code == 404
        assert (await client.get(f'{url}/content', params={"revision": current["revision"]})).status_code == 404
