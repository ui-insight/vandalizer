"""Explicit workflow saves can replace deleted Pages without reviving old links."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services import artifacts
from tests.test_artifacts import db as db, route_env as route_env
from tests.test_chat_routes import _auth
from tests.test_workflow_pages import result


def delete(db, doc):
    db.html_artifacts.update_one({"uuid": doc["uuid"]}, {"$set": {
        "deleted_at": datetime.now(timezone.utc), "revisions": [],
        "public_token": None, "published_revision": None, "publications": [],
    }})


@pytest.mark.parametrize("step", [None, "review"])
async def test_save_delete_save_creates_new_private_page_from_same_run(client, db, route_env, step):
    run = result("<h1>Original run output</h1>")
    run["steps_output"] = {"review": {"output": "<h1>Selected step output</h1>"}}
    db.activity_event.docs.append({"workflow_session_id": "run1", "user_id": "testuser", "project_uuid": "project1"})
    cookies, headers = _auth()
    url = "/api/pages/from-workflow/run1" + (f"?step={step}" if step else "")
    with patch("app.services.workflow_service._get_authorized_workflow_result", AsyncMock(return_value=SimpleNamespace(model_dump=lambda: run))):
        first = await client.post(url, cookies=cookies, headers=headers)
        assert first.status_code == 200
        old = artifacts.get(db, first.json()["uuid"])
        old = artifacts.revise(db, old, "Edited copy", "<h1>Edited copy</h1>", old["latest_revision"])
        old = artifacts.publish(db, old, old["latest_revision"])
        old_token = old["public_token"]
        artifacts.share_team(db, old, "team1", old["latest_revision"])
        assert (await client.delete(f'/api/pages/{old["uuid"]}', cookies=cookies, headers=headers)).status_code == 200
        tombstone = db.html_artifacts.find_one({"uuid": old["uuid"]})

        saved = await client.post(url, cookies=cookies, headers=headers)
        assert saved.status_code == 200, saved.text
        replacement = artifacts.get(db, saved.json()["uuid"])
        assert replacement["uuid"] != old["uuid"]
        assert replacement["team_id"] is None and replacement["team_revision"] is None
        assert replacement["public_token"] is None and replacement["published_revision"] is None
        assert replacement["publications"] == [] and len(replacement["revisions"]) == 1
        assert replacement["source"]["session_id"] == "run1"
        assert replacement["source"]["step"] == step
        assert replacement["project_uuid"] == "project1"
        assert replacement["title"] == ("Selected step output" if step else "Original run output")
        assert "Edited copy" not in artifacts.revision(replacement)["html"]
        assert db.html_artifacts.find_one({"uuid": old["uuid"]}) == tombstone
        assert (await client.get(f'/api/pages/{old["uuid"]}')).status_code == 404
        assert (await client.get(f"/api/pages/public/{old_token}")).status_code == 404
        again = await client.post(url, cookies=cookies, headers=headers)
        assert again.json()["uuid"] == replacement["uuid"]

        assert (await client.delete(f'/api/pages/{replacement["uuid"]}', cookies=cookies, headers=headers)).status_code == 200
        third = await client.post(url, cookies=cookies, headers=headers)
        assert third.status_code == 200
        assert third.json()["uuid"] not in {old["uuid"], replacement["uuid"]}
        assert (await client.post(url, cookies=cookies, headers=headers)).json()["uuid"] == third.json()["uuid"]
        assert len(db.html_artifacts.docs) == 3


def test_automatic_retry_does_not_recreate_deleted_page_but_reuses_manual_replacement(db):
    run = {**result(), "_id": "result1"}
    db.workflow_result.docs.append(deepcopy(run))
    original = artifacts.deliver_workflow_artifact(db, run, "testuser")
    delete(db, artifacts.get(db, original["artifact_uuid"]))
    retry = artifacts.deliver_workflow_artifact(db, run, "testuser")
    assert retry["status"] == "failed" and "Save as page" in retry["error"]
    assert len(db.html_artifacts.docs) == 1
    new = artifacts.from_workflow(db, run, "testuser", recreate_deleted=True)
    assert artifacts.deliver_workflow_artifact(db, run, "testuser")["artifact_uuid"] == new["uuid"]
    assert db.workflow_result.docs[0]["hosted_artifact_uuid"] == new["uuid"]
    assert db.workflow_result.docs[0]["delivery_failures"] == []
    assert len(db.html_artifacts.docs) == 2
    delete(db, new)
    with pytest.raises(HTTPException) as failure:
        artifacts.from_workflow(db, run, "testuser")
    assert failure.value.status_code == 410 and len(db.html_artifacts.docs) == 2


def test_interleaved_saves_reuse_the_same_replacement(db, monkeypatch):
    run = result()
    delete(db, artifacts.from_workflow(db, run, "testuser"))
    create = artifacts.create
    competing = []

    def create_after_competitor(*args, **kwargs):
        monkeypatch.setattr(artifacts, "create", create)
        competing.append(artifacts.from_workflow(db, run, "testuser", recreate_deleted=True))
        return create(*args, **kwargs)

    monkeypatch.setattr(artifacts, "create", create_after_competitor)
    saved = artifacts.from_workflow(db, run, "testuser", recreate_deleted=True)
    assert saved["uuid"] == competing[0]["uuid"]
    assert len(db.html_artifacts.docs) == 2


def test_replacements_stay_scoped_to_the_owner_and_step(db):
    run = result()
    run["steps_output"] = {"review": {"output": "<h1>Step result</h1>"}}
    original = artifacts.from_workflow(db, run, "testuser")
    other_user = artifacts.from_workflow(db, run, "other")
    step = artifacts.from_workflow(db, run, "testuser", "review")
    delete(db, original)
    replacement = artifacts.from_workflow(db, run, "testuser", recreate_deleted=True)
    assert artifacts.from_workflow(db, run, "other") == other_user
    assert artifacts.from_workflow(db, run, "testuser", "review") == step
    assert replacement["uuid"] not in {original["uuid"], other_user["uuid"], step["uuid"]}
