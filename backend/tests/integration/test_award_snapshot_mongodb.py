"""Award snapshot on MongoDB: build, live deadlines, rebuild on document change, Page, routes.

Support ticket: a project held an award's documents and RA inbox deadlines,
but nothing showed where the award stood, and a saved page went stale as
soon as a deadline was marked Done. The project below is the ticket's NIH
subaward. The model call is the only thing replaced: the engine returns the
entities a model would, with source passages, and everything else is real.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_award_snapshot_mongodb.py
"""

import datetime
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.award_snapshot import AwardSnapshot
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.obligation import Obligation, ObligationSource
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.routers import award_snapshots as snapshot_router
from app.services import award_snapshot, obligation_service
from app.services.extraction_sources import SOURCE_KEY

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

SUBAWARD_TEXT = (
    "RESEARCH SUBAWARD AGREEMENT\nPass-through entity: Washington State University\n"
    "Prime sponsor: National Institutes of Health. Prime award R01AI123456.\nSubaward No. WSU-UI-2025-1132\n"
    "Period of performance: January 1, 2026 through December 31, 2027.\n"
    "Total subaward amount: $243,200. F&A: 52% MTDC.\nBudget: Year 1 $121,600; Year 2 $121,600.\n"
)
ENTITY = {
    "Sponsor": "National Institutes of Health",
    "Subaward number": "WSU-UI-2025-1132",
    "Total award amount": "$243,200",
    "F&A rate": "52% MTDC",
    "Budget period 1 amount": "$121,600",
    "Budget period 2 amount": "$121,600",
    SOURCE_KEY: {
        "Sponsor": {"quote": "Prime sponsor: National Institutes of Health", "document_uuid": "subaward",
                    "document_title": "Subaward WSU-UI-2025-1132.pdf", "page": 1, "support": "supported"},
        "Total award amount": {"quote": "Total subaward amount: $243,200", "document_uuid": "subaward",
                               "document_title": "Subaward WSU-UI-2025-1132.pdf", "page": 2, "support": "supported"},
    },
}


@pytest.fixture
def sync_db(sync_mongo):
    with patch("app.tasks.get_sync_db", return_value=sync_mongo):
        yield sync_mongo


async def _setup(today):
    owner = User(user_id="ra-owner", email="o@example.test", name="RA Owner")
    viewer = User(user_id="pi", email="pi@example.test", name="PI")
    await owner.insert()
    await viewer.insert()
    await SmartFolder(uuid="root", parent_id="0", title="NIH Subaward", user_id="ra-owner").insert()
    await Project(uuid="proj", title="NIH Subaward WSU-UI-2025-1132", owner_user_id="ra-owner",
                  root_folder_uuid="root", state="awarded").insert()
    await ProjectMembership(project_uuid="proj", user_id="pi", role="viewer").insert()
    await SmartDocument(uuid="subaward", title="Subaward WSU-UI-2025-1132.pdf", path="x", downloadpath="x",
                        user_id="ra-owner", folder="root", raw_text=SUBAWARD_TEXT, token_count=120,
                        text_markers=[{"char_offset": 0, "kind": "page", "value": 1}]).insert()
    src = [ObligationSource(document_uuid="subaward", document_title="Subaward WSU-UI-2025-1132.pdf", page=4,
                            quote="Validated qPCR assay protocol due within 60 days.")]
    d = datetime.timedelta
    for uuid, title, due, status in [
        ("qpcr", "Validated qPCR assay protocol", today - d(121), "open"),
        ("results", "Semi-annual results", today + d(14), "open"),
        ("final", "Final invoice and technical report", today + d(500), "open"),
        ("kickoff", "Kickoff memo", today - d(200), "done"),
    ]:
        await Obligation(uuid=uuid, project_uuid="proj", kind="deadline", title=title, created_by="ra-owner",
                         due_at=datetime.datetime(due.year, due.month, due.day), status=status, sources=src).insert()
    return owner, viewer


def _client(user):
    app = FastAPI()
    app.include_router(snapshot_router.router, prefix="/api/projects")
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_build_view_live_deadlines_and_rebuild(mongo_client, sync_db):
    from app.services.deadline_reminders import today_local

    today = today_local()
    owner, viewer = await _setup(today)
    project = await Project.find_one(Project.uuid == "proj")

    # Before a build: deadlines and status are already there, facts are not.
    v = await award_snapshot.view(project, viewer)
    assert v["status"] == "not_built" and v["facts"] == []
    assert [d["title"] for d in v["deadlines"]["overdue"]] == ["Validated qPCR assay protocol"]
    assert v["deadlines"]["overdue"][0]["days_until"] == -121
    assert [d["title"] for d in v["deadlines"]["upcoming"]] == ["Semi-annual results", "Final invoice and technical report"]
    assert [d["title"] for d in v["deadlines"]["done"]] == ["Kickoff memo"]
    assert v["project"]["state"] == "awarded" and v["can_manage"] is False

    # Build: queued, then run (the task body, with the model call replaced).
    sent = []
    with patch("app.services.award_snapshot._dispatch", side_effect=lambda *a, **k: sent.append((a, k))):
        await award_snapshot.request_build(project, owner)
    snap = await AwardSnapshot.find_one(AwardSnapshot.project_uuid == "proj")
    assert snap.status == "building" and sent[0][0] == ("proj", snap.build_token)
    with patch("app.services.extraction_engine.ExtractionEngine.extract", return_value=[ENTITY]) as extract, \
         patch("app.tasks.extraction_tasks._get_user_model_name", return_value="test-model"):
        assert award_snapshot.build_sync("proj", snap.build_token) == "ready"
    kwargs = extract.call_args.kwargs
    assert kwargs["capture_sources"] is True and kwargs["doc_metadata"][0]["uuid"] == "subaward"

    v = await award_snapshot.view(project, owner)
    facts = {f["label"]: f for f in v["facts"]}
    assert facts["Total amount"]["value"] == "$243,200" and facts["Total amount"]["page"] == 2
    assert facts["Subaward number"]["support"] == "unverified", "no passage: kept, marked"
    assert [y["value"] for y in v["budget_years"]] == ["$121,600", "$121,600"]
    assert v["status"] == "ready" and v["out_of_date"] is False and v["can_manage"] is True

    # Marking a deadline Done changes the snapshot at once — no rebuild.
    qpcr = await Obligation.find_one(Obligation.uuid == "qpcr")
    await obligation_service.set_done(qpcr, owner, True)
    v = await award_snapshot.view(project, owner)
    assert v["deadlines"]["overdue"] == []
    assert "Validated qPCR assay protocol" in [d["title"] for d in v["deadlines"]["done"]]

    # A build overtaken by a newer request while it reads writes nothing.
    running = (await AwardSnapshot.find_one(AwardSnapshot.project_uuid == "proj"))
    with patch("app.services.award_snapshot._dispatch"):
        await award_snapshot.request_build(project, owner)
    token = (await AwardSnapshot.find_one(AwardSnapshot.project_uuid == "proj")).build_token

    def overtaken(*args, **kwargs):
        sync_db.award_snapshot.update_one({"project_uuid": "proj"}, {"$set": {"build_token": "newer"}})
        return [{"Sponsor": "Overtaken Sponsor"}]

    with patch("app.services.extraction_engine.ExtractionEngine.extract", side_effect=overtaken), \
         patch("app.tasks.extraction_tasks._get_user_model_name", return_value="test-model"):
        assert award_snapshot.build_sync("proj", token) == "superseded"
    stored = sync_db.award_snapshot.find_one({"project_uuid": "proj"})
    assert [f["value"] for f in stored["facts"] if f["label"] == "Sponsor"] == ["National Institutes of Health"]
    assert running is not None
    # (The newer build finishes.)
    sync_db.award_snapshot.update_one({"project_uuid": "proj"}, {"$set": {"status": "ready"}})

    # A new document in the project: out of date, and its ingestion queues a rebuild.
    await SmartDocument(uuid="budget", title="Budget justification.pdf", path="y", downloadpath="y",
                        user_id="ra-owner", folder="root", raw_text="Budget", token_count=30).insert()
    assert (await award_snapshot.view(project, owner))["out_of_date"] is True
    with patch("app.services.award_snapshot._dispatch") as dispatch:
        assert award_snapshot.queue_rebuild_for_document_sync(sync_db, {"uuid": "budget", "folder": "root"}) is True
    assert dispatch.call_args.kwargs["countdown"] == award_snapshot.REBUILD_DELAY_SECONDS
    assert (await AwardSnapshot.find_one(AwardSnapshot.project_uuid == "proj")).status == "building"


async def test_no_automatic_build_before_someone_asks(mongo_client, sync_db):
    from app.services.deadline_reminders import today_local

    owner, _viewer = await _setup(today_local())
    with patch("app.services.award_snapshot._dispatch") as dispatch:
        assert award_snapshot.queue_rebuild_for_document_sync(sync_db, {"uuid": "subaward", "folder": "root"}) is False
        # Share as Page leaves a snapshot row that was never built: still no
        # automatic (paid) build until someone asks for one.
        project = await Project.find_one(Project.uuid == "proj")
        await award_snapshot.share_as_page(project, owner)
        assert award_snapshot.queue_rebuild_for_document_sync(sync_db, {"uuid": "subaward", "folder": "root"}) is False
    dispatch.assert_not_called()


async def test_routes_share_as_page_and_permissions(mongo_client, sync_db):
    from app.services.deadline_reminders import today_local

    owner, viewer = await _setup(today_local())
    async with _client(viewer) as http:
        got = await http.get("/api/projects/proj/award-snapshot")
        assert got.status_code == 200 and got.json()["deadlines"]["overdue"][0]["title"] == "Validated qPCR assay protocol"
        assert (await http.post("/api/projects/proj/award-snapshot/build")).status_code == 403
        assert (await http.post("/api/projects/proj/award-snapshot/page")).status_code == 403
    outsider = User(user_id="outsider", email="x@example.test", name="X")
    await outsider.insert()
    async with _client(outsider) as http:
        assert (await http.get("/api/projects/proj/award-snapshot")).status_code == 404

    async with _client(owner) as http:
        with patch("app.services.award_snapshot._dispatch"):
            built = await http.post("/api/projects/proj/award-snapshot/build")
        assert built.status_code == 200 and built.json()["status"] == "building"
        first = (await http.post("/api/projects/proj/award-snapshot/page")).json()
        page = sync_db.html_artifacts.find_one({"uuid": first["uuid"]})
        assert page["project_uuid"] == "proj" and page["team_id"] is None and page["public_token"] is None
        html = page["revisions"][-1]["html"]
        assert "Validated qPCR assay protocol" in html and "This page is a copy" in html

        # Sharing again after a change adds a revision to the same page.
        await obligation_service.set_done(await Obligation.find_one(Obligation.uuid == "qpcr"), owner, True)
        second = (await http.post("/api/projects/proj/award-snapshot/page")).json()
        assert second["uuid"] == first["uuid"] and second["revision"] != first["revision"]
        assert len(sync_db.html_artifacts.find_one({"uuid": first["uuid"]})["revisions"]) == 2
        assert (await http.get("/api/projects/proj/award-snapshot")).json()["page_uuid"] == first["uuid"]
