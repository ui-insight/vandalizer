"""Artifact contracts, authorization and immutable-publication boundaries."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.services import artifacts
from app.services.access_control import TeamAccessContext
from tests.test_chat_routes import _auth, _make_user


class Collection:
    def __init__(self):
        self.docs = []

    def matches(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self.matches(doc, q) for q in value):
                    return False
            elif isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def find_one(self, query):
        return deepcopy(next((d for d in self.docs if self.matches(d, query)), None))

    def find_one_and_update(self, query, update, upsert=False, **kwargs):
        doc = next((d for d in self.docs if self.matches(d, query)), None)
        if doc is None and upsert:
            doc = {**query, **deepcopy(update.get("$setOnInsert", {}))}
            self.docs.append(doc)
        if doc is None:
            return None
        doc.update(deepcopy(update.get("$set", {})))
        for key, value in update.get("$push", {}).items():
            doc.setdefault(key, []).append(deepcopy(value))
        for key, value in update.get("$addToSet", {}).items():
            if value not in doc.setdefault(key, []):
                doc[key].append(value)
        for key, value in update.get("$pull", {}).items():
            doc[key] = [v for v in doc.get(key, []) if v != value]
        return deepcopy(doc)

    def update_one(self, query, update):
        return self.find_one_and_update(query, update)


@pytest.fixture
def db():
    return SimpleNamespace(html_artifacts=Collection(), chat_page_previews=Collection(), workflow=Collection(), workflow_result=Collection(), activity_event=Collection())


def make(db, key="one", owner="testuser", html="<main><h1>Original</h1></main>"):
    return artifacts.create(db, owner, "Review", html, key, {"kind": "chat", "conversation_uuid": "private-chat"})


def test_sanitized_self_contained_html_has_no_active_or_remote_elements():
    html, warnings = artifacts.clean_html('''<html><head><base href="https://evil.test"><style>body{color:red;background:url(https://evil.test/track)}</style></head><body onload="steal()"><script>steal()</script><iframe src="/api/auth/me"></iframe><form action="https://evil.test"><input name="secret"></form><svg onload="steal()"></svg><img src="https://evil.test/track"><img src="data:image/png;base64,AAAA"><a href="javascript:steal()">bad</a><h1>Report</h1></body></html>''', 'Test <script>')
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.select("script, iframe, form, input, svg, base")
    assert "onload" not in html
    assert soup.select_one('a').get("href") is None
    assert all(not img.get("src", "").startswith("http") for img in soup.select("img"))
    csp = soup.select_one('meta[http-equiv="Content-Security-Policy"]')["content"]
    assert "sandbox" in csp and "script-src 'none'" in csp and "connect-src 'none'" in csp
    assert "style-src 'unsafe-inline'" in csp and "img-src data:" in csp
    assert soup.h1.text == "Report" and warnings


def test_static_budget_dashboard_preserves_rows_values_and_css_bars():
    html = '''<main><h1>Budget overview (static)</h1><p>Total: $150,000</p>
        <figure><figcaption>Budget by Category and Year</figcaption>
        <div style="width:66.7%;background:navy">Personnel: $100,000</div>
        <div style="width:33.3%;background:teal">Equipment: $50,000</div></figure>
        <table><thead><tr><th>Category</th><th>Year 1</th></tr></thead>
        <tbody><tr><td>Personnel</td><td>$100,000</td></tr>
        <tr><td>Equipment</td><td>$50,000</td></tr></tbody></table></main>'''
    cleaned, warnings = artifacts.clean_html(html, "Budget")
    soup = BeautifulSoup(cleaned, "html.parser")
    assert warnings == []
    assert [row.get_text('|') for row in soup.select('tbody tr')] == [
        'Personnel|$100,000', 'Equipment|$50,000',
    ]
    assert [bar.text for bar in soup.select('figure div')] == ['Personnel: $100,000', 'Equipment: $50,000']
    assert soup.select_one('figure div')['style'] == 'width:66.7%;background:navy'


@pytest.mark.asyncio
async def test_script_dashboard_warnings_reach_preview_save_read_and_revision(db):
    from app.services.chat_artifact_tools import create_html_artifact, get_html_artifact, revise_html_artifact
    from app.services.chat_deps import AgenticChatDeps

    conversation = SimpleNamespace(uuid="dashboard-chat", pending_confirmations=[], save=AsyncMock())
    deps = AgenticChatDeps(user=_make_user(), user_id="testuser", team_id=None,
        team_access=TeamAccessContext(), organization_id=None, system_config_doc={},
        model_name="test", conversation=conversation, turn_marker=1)
    context = SimpleNamespace(deps=deps)
    html = '''<main><h1>Budget</h1><p>Total: $150,000</p>
        <h2>Budget by Category and Year</h2><canvas id="chart"></canvas>
        <h2>Budget Distribution</h2><canvas id="pie"></canvas>
        <div>Filter by Category: <button onclick="filter()">Personnel</button></div>
        <table><thead><tr><th onclick="sort()">Category</th></tr></thead><tbody></tbody></table>
        <script>document.querySelector('tbody').innerHTML = '<tr><td>Personnel</td></tr>';</script></main>'''
    with patch("app.services.chat_artifact_tools.get_sync_db", return_value=db):
        preview = await create_html_artifact(context, "Budget", html)
        assert preview["needs_confirmation"] and not db.html_artifacts.docs
        assert '"Save page" button' in preview['assistant_instruction']
        assert 'artifact' not in preview['assistant_instruction']
        soup = BeautifulSoup(preview["artifact_preview_html"], "html.parser")
        assert not soup.select('script, canvas, button, [onclick]')
        assert '$150,000' in soup.text
        assert "Data rendered only by scripts will be missing" in preview["warnings"][0]
        assert "table sorting are not supported" in preview["rendering_note"]

        deps.turn_marker = 2
        saved = await create_html_artifact(context, "Budget", html, confirmed=True)
        read = await get_html_artifact(context, saved["artifact_uuid"])
        assert read["html"] == preview["artifact_preview_html"]
        assert saved["warnings"] == read["warnings"] == preview["warnings"]
        assert saved["rendering_note"] == read["rendering_note"] == preview["rendering_note"]
        assert saved['version'] == read['version'] == 1
        from app.services.page_authoring import PAGE_LANGUAGE_RULES
        assert saved['language_note'] == read['language_note'] == preview['language_note'] == PAGE_LANGUAGE_RULES
        from app.services.page_authoring import PAGE_SOURCE_FIDELITY_RULES
        assert saved["source_fidelity_note"] == read["source_fidelity_note"] == preview["source_fidelity_note"] == PAGE_SOURCE_FIDELITY_RULES

        # A retry using the sanitized HTML must still report the stored warnings.
        retry_preview = await create_html_artifact(context, "Budget", read["html"])
        assert retry_preview["needs_confirmation"]
        deps.turn_marker = 3
        retry = await create_html_artifact(context, "Budget", read["html"], confirmed=True)
        assert retry["artifact_uuid"] == saved["artifact_uuid"]
        assert retry["warnings"] == saved["warnings"]

        revised_html = html.replace('$150,000', '$160,000')
        revision_preview = await revise_html_artifact(context, saved["artifact_uuid"], saved["revision"], "Budget", revised_html)
        assert '"Save new version" button' in revision_preview['assistant_instruction']
        assert 'artifact' not in revision_preview['assistant_instruction']
        assert revision_preview["warnings"] == preview["warnings"]
        deps.turn_marker = 4
        revised = await revise_html_artifact(context, saved["artifact_uuid"], saved["revision"], "Budget", revised_html, confirmed=True)
        assert revised["warnings"] == revision_preview["warnings"]
        assert revised["source_fidelity_note"] == revision_preview["source_fidelity_note"] == PAGE_SOURCE_FIDELITY_RULES
        assert revised["revision"] != saved["revision"]
        assert revised['version'] == 2


def test_create_retry_and_revision_cas_and_public_pin(db):
    doc = make(db)
    assert make(db)["uuid"] == doc["uuid"] and len(db.html_artifacts.docs) == 1
    with pytest.raises(HTTPException) as exc:
        make(db, html="<p>Different payload</p>")
    assert exc.value.status_code == 409
    published = artifacts.publish(db, doc, doc["latest_revision"])
    changed = artifacts.revise(db, published, "Changed", "<p>New private content</p>", published["latest_revision"])
    assert changed["published_revision"] == doc["latest_revision"]
    assert "Original" in artifacts.revision(changed, changed["published_revision"])["html"]
    assert "New private content" in artifacts.revision(changed)["html"]
    retry = artifacts.revise(db, changed, "Changed", "<p>New private content</p>", published["latest_revision"])
    assert len(retry["revisions"]) == 2
    with pytest.raises(HTTPException) as exc:
        artifacts.revise(db, published, "Competing edit", "<p>Conflict</p>", published["latest_revision"])
    assert exc.value.status_code == 409


def test_size_revision_limit_and_html_workflow_inputs(db):
    with pytest.raises(HTTPException, match="256 KiB"):
        artifacts.clean_html("é" * 140000, "Large")
    with pytest.raises(HTTPException, match="valid Unicode"):
        artifacts.clean_html("\ud800", "Invalid")
    assert 'href=' not in artifacts.clean_html('<a href="https://[">Malformed link</a>', "Links")[0]
    doc = make(db)
    doc["revisions"] *= 25
    with pytest.raises(HTTPException, match="25 revisions"):
        artifacts.revise(db, doc, "Next", "<p>Next</p>", doc["latest_revision"])
    assert artifacts.workflow_html('```html\n<main>Report</main>\n```', "Report") == "<main>Report</main>"
    assert "<table>" in artifacts.workflow_html([{"Amount": 25}], "Report")
    with pytest.raises(HTTPException, match="binary file"):
        artifacts.workflow_html({"type": "file_download", "data": "base64"}, "Report")


@pytest.mark.parametrize("html", ["é" * 140000, "x" * (artifacts.MAX_HTML_BYTES - 1)])
def test_page_size_limit_explains_how_to_recover_without_saving(db, html):
    with pytest.raises(HTTPException) as error:
        artifacts.create(db, "owner", "All tabs", html, "large-page")
    assert artifacts.PAGE_TOO_LARGE_MESSAGE in error.value.detail
    assert db.html_artifacts.docs == []


def test_workflow_delivery_retry_has_one_private_artifact_and_provenance(db):
    db.workflow.docs.append({"_id": "wf1", "name": "Award review", "user_id": "testuser"})
    result = {"_id": "run1", "workflow": "wf1", "session_id": "session1", "status": "completed", "final_output": {"output": "<main><h1>Workflow</h1></main>"}}
    db.workflow_result.docs.append(deepcopy(result))
    first = artifacts.deliver_workflow_artifact(db, result, "testuser")
    second = artifacts.deliver_workflow_artifact(db, result, "testuser")
    assert first == second and first["status"] == "completed"
    assert len(db.html_artifacts.docs) == 1
    doc = artifacts.get(db, first["artifact_uuid"])
    assert doc["public_token"] is None and doc["team_id"] is None
    assert artifacts.revision(doc)["source"]["session_id"] == "session1"
    assert db.workflow_result.docs[0]["hosted_artifact_uuid"] == doc["uuid"]
    result["status"] = "failed"
    failure = artifacts.deliver_workflow_artifact(db, result, "testuser")
    assert failure["status"] == "failed" and db.workflow_result.docs[0]["delivery_failures"]


@pytest.fixture
def route_env(db):
    from app.main import app
    user = _make_user()
    settings = Settings(artifact_public_sharing_enabled=True)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings
    access = AsyncMock(return_value=TeamAccessContext())
    with patch("app.routers.artifacts.get_sync_db", return_value=db), patch("app.routers.artifacts.access_control.get_team_access_context", access):
        yield SimpleNamespace(user=user, settings=settings, access=access)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_settings, None)


@pytest.mark.asyncio
async def test_exact_yearly_budget_values_survive_revision_and_publication(client, db, route_env, tmp_path):
    """Reconstruct the ticket's two rows; this checks transport, not LLM accuracy."""
    from openpyxl import Workbook
    from app.services.document_readers import extract_text_from_xlsx

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet.append(["Category", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"])
    sheet.append(["Indirect", 51000, 53000, 55000, 57000, 49000])
    sheet.append(["Other", 10000, 10000, 10000, 10000, 10000])
    source_path = tmp_path / "budget-regression.xlsx"
    workbook.save(source_path)
    workbook.close()
    source = extract_text_from_xlsx(str(source_path))
    assert '| Indirect | 51000 | 53000 | 55000 | 57000 | 49000 |' in source
    assert '| Other | 10000 | 10000 | 10000 | 10000 | 10000 |' in source
    assert 'range' not in source.lower()

    # The model's job is to preserve these cells. Exercise the actual static
    # rendering and public route separately so a model regression isn't hidden
    # by a test that merely supplies a canned model response.
    html = artifacts.workflow_html(source, "Budget")
    first = make(db, html="<h1>Budget draft</h1>")
    second = artifacts.revise(db, first, "Budget", html, first["latest_revision"])
    assert not second["published_revision"]
    cookies, headers = _auth()
    published = await client.put(f'/api/pages/{first["uuid"]}/publication',
        json={"revision": second["latest_revision"]}, cookies=cookies, headers=headers)
    assert published.status_code == 200
    response = await client.get(f'/api/pages/public/{published.json()["public_token"]}/content')
    assert response.status_code == 200
    assert response.text == artifacts.revision(second)["html"]
    soup = BeautifulSoup(response.text, 'html.parser')
    rows = [[cell.get_text(strip=True) for cell in row.select('th, td')] for row in soup.select('tr')]
    assert rows == [
        ['Category', 'Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5'],
        ['Indirect', '51000', '53000', '55000', '57000', '49000'],
        ['Other', '10000', '10000', '10000', '10000', '10000'],
    ]
    assert 'range' not in soup.get_text().lower()


@pytest.mark.asyncio
async def test_private_access_team_membership_and_owner_only_mutations(client, db, route_env):
    doc = make(db)
    uid, rev = doc["uuid"], doc["latest_revision"]
    cookies, headers = _auth()
    assert (await client.get(f"/api/pages/{uid}")).status_code == 200
    route_env.user.user_id = "other-user"
    for suffix in ["", f"/revisions/{rev}/content", f"/revisions/{rev}/source"]:
        assert (await client.get(f"/api/pages/{uid}{suffix}")).status_code == 404
    db.html_artifacts.update_one({"uuid": uid}, {"$set": {"team_id": "team-a"}})
    route_env.access.return_value = TeamAccessContext(team_uuids={"team-a"})
    assert (await client.get(f"/api/pages/{uid}")).status_code == 200
    assert (await client.get(f"/api/pages/{uid}/revisions/{rev}/content")).status_code == 200
    assert (await client.get(f"/api/pages/{uid}/revisions/{rev}/source")).status_code == 404
    assert (await client.put(f"/api/pages/{uid}/publication", json={"revision": rev}, cookies=cookies, headers=headers)).status_code == 404
    route_env.access.return_value = TeamAccessContext()
    assert (await client.get(f"/api/pages/{uid}")).status_code == 404


@pytest.mark.asyncio
async def test_public_revision_no_private_metadata_revocation_rotation_and_operator_switch(client, db, route_env):
    doc = make(db)
    uid, rev = doc["uuid"], doc["latest_revision"]
    cookies, headers = _auth()
    response = await client.put(f"/api/pages/{uid}/publication", json={"revision": rev}, cookies=cookies, headers=headers)
    token = response.json()["public_token"]
    artifacts.revise(db, artifacts.get(db, uid), "Secret draft", "<p>Not published</p>", rev)
    response = await client.get(f"/api/pages/public/{token}")
    from fastapi.encoders import jsonable_encoder
    assert response.json() == jsonable_encoder({"title": "Review", "revision": rev,
        "version": 1, "updated_at": doc["revisions"][0]["created_at"]})
    content = await client.get(f"/api/pages/public/{token}/content")
    assert "Original" in content.text and "Not published" not in content.text
    assert "private-chat" not in content.text
    assert content.headers["cache-control"] == "no-store"
    assert content.headers["x-frame-options"] == "SAMEORIGIN"
    assert content.headers["content-security-policy"] == artifacts.CONTENT_CSP
    route_env.settings.artifact_public_sharing_enabled = False
    assert (await client.get(f"/api/pages/public/{token}/content")).status_code == 404
    assert (await client.put(f"/api/pages/{uid}/publication", json={"revision": rev}, cookies=cookies, headers=headers)).status_code == 403
    route_env.settings.artifact_public_sharing_enabled = True
    assert (await client.delete(f"/api/pages/{uid}/publication", cookies=cookies, headers=headers)).status_code == 200
    assert (await client.get(f"/api/pages/public/{token}/content")).status_code == 404
    response = await client.put(f"/api/pages/{uid}/publication", json={"revision": rev}, cookies=cookies, headers=headers)
    assert response.json()["public_token"] != token
    assert (await client.delete(f"/api/pages/{uid}", cookies=cookies, headers=headers)).status_code == 200
    assert (await client.get(f"/api/pages/{uid}")).status_code == 404
    assert (await client.get(f'/api/pages/public/{response.json()["public_token"]}/content')).status_code == 404
    with pytest.raises(HTTPException) as exc:
        make(db)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_unauthenticated_private_denied_public_allowed(client, db):
    doc = make(db)
    public = artifacts.publish(db, doc, doc["latest_revision"])
    with patch("app.routers.artifacts.get_sync_db", return_value=db):
        assert (await client.get(f'/api/pages/{doc["uuid"]}')).status_code == 401
        response = await client.get(f'/api/pages/public/{public["public_token"]}/content')
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_tool_approval_is_bound_to_exact_html_and_keeps_skill_provenance(db):
    from app.services.chat_artifact_tools import create_html_artifact, revise_html_artifact
    from app.services.chat_deps import AgenticChatDeps
    conversation = SimpleNamespace(uuid="chat1", pending_confirmations=[], save=AsyncMock(), active_skill=SimpleNamespace(uuid="skill1", version="v1"))
    deps = AgenticChatDeps(user=_make_user(), user_id="testuser", team_id=None, team_access=TeamAccessContext(), organization_id=None, system_config_doc={}, model_name="test", conversation=conversation, turn_marker=1)
    context = SimpleNamespace(deps=deps)
    with patch("app.services.chat_artifact_tools.get_sync_db", return_value=db):
        preview = await create_html_artifact(context, "Report", "<h1>Approved content</h1>", confirmed=True)
        assert preview["needs_confirmation"] and not db.html_artifacts.docs
        deps.turn_marker = 2
        changed = await create_html_artifact(context, "Report", "<h1>Changed secretly</h1>", confirmed=True)
        assert changed["needs_confirmation"] and not db.html_artifacts.docs
        saved = await create_html_artifact(context, "Report", "<h1>Approved content</h1>", confirmed=True)
        assert saved["artifact_uuid"]
        doc = artifacts.get(db, saved["artifact_uuid"])
        assert artifacts.revision(doc)["source"]["skill"] == {"uuid": "skill1", "version": "v1"}
        assert not doc["public_token"]
        deps.user_id = "other"
        denied = await revise_html_artifact(context, doc["uuid"], doc["latest_revision"], "Hijack", "<h1>Hijack</h1>", True)
        assert "error" in denied


@pytest.mark.parametrize("passive", [False, True])
def test_manual_worker_delivers_only_manual_runs_to_the_launcher(passive):
    from tests.test_workflow_tasks import _mock_db, _make_workflow_doc, _make_result_doc, _fake_oid
    from app.tasks.workflow_tasks import execute_workflow_task
    workflow = _make_workflow_doc(step_ids=[])
    workflow["output_config"] = {"artifact": {"enabled": True}}
    result = _make_result_doc(workflow_id=workflow["_id"])
    result["is_passive"] = passive
    db = _mock_db(workflow_doc=workflow, result_doc=result, smart_docs=[{"uuid": "uuid1", "raw_text": "text"}])
    db.activity_event.find_one.return_value = {"user_id": "launcher"}
    def update(query, changes):
        result.update(changes.get("$set", {}))
        return SimpleNamespace(modified_count=1)
    db.workflow_result.update_one.side_effect = update
    engine = MagicMock()
    engine.execute.return_value = ("<main>Result</main>", [])
    engine.usage = SimpleNamespace(tokens_in=0, tokens_out=0)
    with patch("app.tasks.workflow_tasks._get_db", return_value=db), patch("app.services.workflow_engine.build_workflow_engine", return_value=engine), patch("app.services.artifacts.deliver_workflow_artifact") as deliver, patch("app.tasks.quality_tasks.auto_validate_workflow"), patch("app.tasks.activity_tasks.generate_activity_description_task"):
        execute_workflow_task(workflow_result_id=str(result["_id"]), workflow_id=str(workflow["_id"]), trigger_step_data={"doc_uuids": ["uuid1"]}, model="test", activity_id=str(_fake_oid()))
    if passive:
        deliver.assert_not_called()
    else:
        deliver.assert_called_once_with(db, result, "launcher")
        assert result["status"] == "completed"


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_passive_output_delivery_uses_the_workflow_owner_and_never_publishes(status):
    from bson import ObjectId
    from app.tasks.passive_tasks import process_outputs
    db = MagicMock()
    result = {"_id": ObjectId(), "workflow": ObjectId(), "session_id": "passive-1", "status": status}
    db.workflow_result.find_one.return_value = result
    db.workflow.find_one.return_value = {"_id": result["workflow"], "user_id": "owner", "output_config": {"artifact": {"enabled": True}}}
    db.workflow_trigger_event.find_one.return_value = None
    db.automation.find_one.return_value = None
    with patch("app.tasks.passive_tasks.get_sync_db", return_value=db), patch("app.services.artifacts.deliver_workflow_artifact", return_value={"status": "completed", "artifact_uuid": "private"}) as deliver:
        output = process_outputs(str(result["_id"]))
    if status == "completed":
        deliver.assert_called_once_with(db, result, "owner")
        assert output["artifact"]["artifact_uuid"] == "private"
    else:
        deliver.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_save_route_authorizes_before_reading_run_output(client, db, route_env):
    cookies, headers = _auth()
    run = {"workflow": "wf1", "session_id": "run1", "status": "completed", "final_output": {"output": "<main>Run output</main>"}}
    with patch("app.services.workflow_service._get_authorized_workflow_result", AsyncMock(return_value=None)) as authorize:
        response = await client.post("/api/pages/from-workflow/run1", cookies=cookies, headers=headers)
        assert response.status_code == 404 and not db.html_artifacts.docs
        authorize.return_value = SimpleNamespace(model_dump=lambda: run)
        first = await client.post("/api/pages/from-workflow/run1", cookies=cookies, headers=headers)
        again = await client.post("/api/pages/from-workflow/run1", cookies=cookies, headers=headers)
    assert first.status_code == again.status_code == 200
    assert first.json()["uuid"] == again.json()["uuid"]
    assert first.json()["source"]["session_id"] == "run1"
    assert first.json()["public_token"] is None
