"""RA routines as workflows: Create project, Add deadlines to RA inbox, Award
snapshot page (support ticket: "RA playbooks")."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import workflow_workspace_steps as ws
from app.services.workflow_engine import build_workflow_engine

STEPS = [
    {"name": "Document", "data": {"doc_uuids": ["DOC1"]}},
    {"name": "Create project", "tasks": [{"name": "CreateProject", "data": {"name_template": "{document}"}}]},
    {"name": "Add deadlines to RA inbox", "tasks": [{"name": "InboxDeadlines", "data": {}}]},
    {"name": "Award snapshot page", "tasks": [{"name": "AwardSnapshotPage", "data": {}}]},
]
PROJECT = "a" * 32


def _steps():
    return json.loads(json.dumps(STEPS))


def test_outside_a_real_run_the_steps_only_describe_what_they_would_do():
    sync_db = MagicMock()
    sync_db.smart_document.find.return_value = [{"uuid": "DOC1", "title": "NIFA_Subaward_2026-0412.pdf"}]
    with patch("app.tasks.get_sync_db", return_value=sync_db), patch.object(ws, "_run") as run:
        engine = build_workflow_engine(_steps(), model="m", user_id="ra")  # validation, Test Step, optimizer…
        _final, steps = engine.execute()
    run.assert_not_called()
    outputs = [s["output"] for s in steps[1:]]
    assert "Would create project “NIFA Subaward 2026-0412”" in outputs[0]
    assert all("Preview only" in o for o in outputs)
    assert not any(node.has_side_effects() for node in engine.get_topological_order())


def test_a_real_run_passes_the_new_project_to_the_later_steps():
    calls = []
    project = SimpleNamespace(uuid=PROJECT, title="NIFA Subaward 2026-0412")

    async def create(user, docs, template):
        calls.append(("create", docs, template))
        return {"project": project, "created": True, "moved": ["NIFA_Subaward_2026-0412.pdf"], "failed": [], "already": []}

    async def deadlines(user, project_uuid, docs, model, cfg):
        calls.append(("deadlines", project_uuid, docs))
        saved = [SimpleNamespace(title="Annual progress report", due_at=None, deadline_calculation=SimpleNamespace(formula="2027-03-01 + 60 calendar days = 2027-04-30"))]
        return {"project": project, "found": 3, "saved": saved, "already": [], "refused": [{"title": "Quarterly reports", "reason": "unsupported relative anchor"}]}

    def snapshot(user, project_uuid):
        calls.append(("snapshot", project_uuid))
        return {"status": "ready", "page": {"uuid": "p" * 32, "title": "NIFA — award snapshot"}, "project": project}

    def run(make):
        return asyncio.run(make())

    with patch.object(ws, "_run", run), patch.object(ws, "create_project_for", create), \
         patch.object(ws, "add_deadlines", deadlines), patch.object(ws, "snapshot_page", snapshot), \
         patch.object(ws._WorkspaceNode, "_user", AsyncMock(return_value=SimpleNamespace(user_id="ra"))):
        engine = build_workflow_engine(_steps(), model="m", user_id="ra", workspace_actions=True)
        _final, steps = engine.execute()
    assert calls == [("create", ["DOC1"], "{document}"), ("deadlines", PROJECT, ["DOC1"]), ("snapshot", PROJECT)]
    assert f"/?project={PROJECT}" in steps[1]["output"]
    assert "2027-03-01 + 60 calendar days = 2027-04-30" in steps[2]["output"]
    # Partial work is a warning on the step, never a clean "Completed".
    assert "1 item found but not added, for review: Quarterly reports" in steps[2]["warning"]
    assert f"/pages/{'p' * 32}" in steps[3]["output"]
    assert all(node.has_side_effects() for node in engine.get_topological_order()[1:])


def test_deadlines_and_pages_need_a_project_step_first():
    steps = [_steps()[0], _steps()[2]]
    with patch.object(ws, "_run") as run:
        engine = build_workflow_engine(steps, model="m", user_id="ra", workspace_actions=True)
        with pytest.raises(Exception) as exc:
            engine.execute()
    run.assert_not_called()
    assert "put a Create project step before this one" in str(exc.value)


def test_project_title_and_link_parsing():
    assert ws.project_title("{document}", ["NIFA_Subaward_2026-0412.pdf"]) == "NIFA Subaward 2026-0412"
    assert ws.project_title("Intake — {document}", ["Award.docx"]) == "Intake — Award"
    inputs = {"output": "x", ws.EARLIER: [{"name": "Document", "output": ["D1", "D2"]},
                                          {"name": "Create project", "output": f"Created project [T](/?project={PROJECT})."}]}
    assert ws.run_documents(inputs) == ["D1", "D2"] and ws.run_project(inputs) == PROJECT
    assert ws.run_project({"output": "nothing", ws.EARLIER: []}) is None


def test_only_real_runs_enable_workspace_actions():
    root = Path(__file__).resolve().parents[1] / "app"
    tasks = (root / "tasks" / "workflow_tasks.py").read_text()
    passive = (root / "tasks" / "passive_tasks.py").read_text()
    assert tasks.count("workspace_actions=True") == 2  # run + resume after approval
    assert passive.count("workspace_actions=True") == 1  # automations
    for builder in ("services/workflow_optimizer.py", "services/run_metadata.py"):
        assert "workspace_actions=True" not in (root / builder).read_text()


def test_chat_can_build_the_routine():
    from app.services.chat_tools import _WORKFLOW_STEP_TYPES, _build_workflow_step_data

    assert _WORKFLOW_STEP_TYPES["create_project"] == ("CreateProject", False)
    data, error = asyncio.run(_build_workflow_step_data(MagicMock(), {"name_template": "{document}"}, "create_project", "m"))
    assert error is None and data == {"name_template": "{document}"}


def test_the_catalog_ships_the_intake_routine_with_one_review_before_setup():
    seed = json.loads((Path(__file__).resolve().parents[1] / "seeds" / "workflows" / "new_subaward_intake.json").read_text())
    names = [s["tasks"][0]["name"] for s in seed["items"][0]["steps"]]
    assert names == ["Extraction", "Approval", "CreateProject", "InboxDeadlines", "AwardSnapshotPage"]
    example = seed["items"][0]["validation_inputs"][0]
    # The answer key quotes the rules it was calculated from. (Anchoring on a
    # stated date or the End Date is calculated by relative_deadlines, #1077.)
    for quote in ("Start Date: September 1, 2026  End Date: August 31, 2027",
                  "The annual progress report is due 60 days after March 1, 2027.",
                  "The final technical report is due 120 days after the End Date.",
                  "The greenhouse trial dataset is due December 15, 2026."):
        assert quote in example["text"]
    for answer in ("April 30, 2027", "December 29, 2027", "December 15, 2026"):
        assert answer in example["label"]


def test_only_a_create_project_report_names_the_runs_project():
    # A prompt step's answer (or a document it echoes) can carry a project link;
    # it must not redirect where the inbox and snapshot steps write.
    other = "b" * 32
    echoed = {"output": f"See the award at https://x.edu/?project={other} for details.", ws.EARLIER: [
        {"name": "Document", "output": ["D1"]},
        {"name": "Summarize", "output": f"Created by the PI. Link: [old](/?project={other})"},
    ]}
    assert ws.run_project(echoed) is None
    reused = {"output": "x", ws.EARLIER: [
        {"name": "Create project", "output": f"The file is already in project [A [draft] award](/?project={PROJECT}), so it was reused."},
        {"name": "Summarize", "output": f"[old](/?project={other})"},
    ]}
    assert ws.run_project(reused) == PROJECT


def test_the_snapshot_step_checks_edit_access_before_building():
    project = SimpleNamespace(uuid=PROJECT, title="Award")
    sync_db = MagicMock()
    with patch.object(ws, "_run", lambda make: asyncio.run(make())), \
         patch("app.tasks.get_sync_db", return_value=sync_db), \
         patch("app.services.project_service.get_authorized_project", AsyncMock(return_value=project)), \
         patch("app.services.project_service.can_manage_project", AsyncMock(return_value=False)), \
         patch("app.services.award_snapshot.build_sync") as build:
        with pytest.raises(RuntimeError, match="edit access"):
            ws.snapshot_page(SimpleNamespace(user_id="viewer"), PROJECT)
    sync_db.award_snapshot.update_one.assert_not_called()
    build.assert_not_called()
