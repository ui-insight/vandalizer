"""RA routine workspace steps on MongoDB: create the project once, add checked deadlines.

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_workflow_workspace_steps_mongodb.py
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.obligation import Obligation
from app.models.project import Project
from app.models.user import User
from app.services import workflow_workspace_steps as ws

pytestmark = [
    pytest.mark.integration_tier2,
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

TEXT = (
    "Research Subaward Agreement\n"
    "Start Date: September 1, 2026  End Date: August 31, 2027\n"
    "4. The greenhouse trial dataset is due December 15, 2026.\n"
    "5. A subject invention disclosure must be submitted for any invention made under this subaward.\n"
)


async def _setup():
    user = User(user_id="ra", email="ra@example.test", name="RA", email_verified=True)
    await user.insert()
    await SmartFolder(uuid="inbox-folder", title="Incoming", parent_id="0", user_id="ra").insert()
    doc = SmartDocument(uuid="DOC1", title="NIFA_Subaward_2026-0412.pdf", path="x", downloadpath="x", user_id="ra",
                        folder="inbox-folder", raw_text=TEXT, extension="pdf")
    await doc.insert()
    return user


ITEMS = [
    {"kind": "deadline", "title": "Greenhouse trial dataset", "deadline_type": "report_due", "due_at": "2026-12-15",
     "sources": [{"document_uuid": "DOC1", "page": None, "quote": "The greenhouse trial dataset is due December 15, 2026.", "role": "evidence"}]},
    {"kind": "required_material", "title": "Subject invention disclosure",
     "sources": [{"document_uuid": "DOC1", "page": None, "quote": "A subject invention disclosure must be submitted for any invention made under this subaward.", "role": "evidence"}]},
    # Not in the document: refused and listed for review, never saved.
    {"kind": "deadline", "title": "Invented kickoff memo", "deadline_type": "other", "due_at": "2026-09-15",
     "sources": [{"document_uuid": "DOC1", "page": None, "quote": "The kickoff memo is due September 15, 2026.", "role": "evidence"}]},
]


async def test_intake_creates_one_project_and_adds_only_checked_items(mongo_client):
    user = await _setup()
    with patch("app.services.knowledge_service.create_knowledge_base", AsyncMock(return_value=type("KB", (), {"uuid": "kb1"})())), \
         patch("app.tasks.document_tasks.sync_project_kb_on_move.delay"):
        first = await ws.create_project_for(user, ["DOC1"], "{document}")
        again = await ws.create_project_for(user, ["DOC1"], "{document}")
    project = first["project"]
    assert first["created"] and project.title == "NIFA Subaward 2026-0412" and first["moved"] == ["NIFA_Subaward_2026-0412.pdf"]
    assert (await SmartDocument.find_one(SmartDocument.uuid == "DOC1")).folder == project.root_folder_uuid
    # Re-running the routine on the same award reuses its project.
    assert again["created"] is False and again["project"].uuid == project.uuid
    assert await Project.find(Project.owner_user_id == "ra").count() == 1
    text, warning = ws.describe_project(first)
    assert f"/?project={project.uuid}" in text and warning is None

    with patch.object(ws, "find_items", AsyncMock(return_value=ITEMS)):
        added = await ws.add_deadlines(user, project.uuid, ["DOC1"], "m", None)
        repeat = await ws.add_deadlines(user, project.uuid, ["DOC1"], "m", None)
    assert sorted(o.title for o in added["saved"]) == ["Greenhouse trial dataset", "Subject invention disclosure"]
    assert [r["title"] for r in added["refused"]] == ["Invented kickoff memo"]
    assert await Obligation.find(Obligation.project_uuid == project.uuid).count() == 2
    text, warning = ws.describe_deadlines(added)
    assert "Added 2 items" in text and "Invented kickoff memo" in warning
    # A second run adds nothing twice.
    assert repeat["saved"] == [] and len(repeat["already"]) == 2
