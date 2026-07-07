"""Tests for project_service serialization — the list/overview shapes the
explorer cards and project home depend on."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import project_service


class _FieldMeta(type):
    """Return a sentinel for any unset class attribute so Beanie-style query
    expressions (e.g. ``Model.uuid == x``) evaluate without ``init_beanie``."""

    def __getattr__(cls, name):
        return f"<field:{name}>"


def _fake_model(constructed: list):
    """A stand-in Beanie model: instances record their kwargs and support the
    async insert()/save() the service awaits, without touching a database."""

    class _Fake(SimpleNamespace, metaclass=_FieldMeta):
        async def insert(self):
            constructed.append(self)

        async def save(self):
            pass

    return _Fake


def _find_returning(*batches):
    """Fake a chained ``Model.find(...).to_list()`` that yields each batch in
    order across successive calls."""
    return MagicMock(
        side_effect=[SimpleNamespace(to_list=AsyncMock(return_value=list(b))) for b in batches]
    )


def _project(**overrides) -> SimpleNamespace:
    base = dict(
        uuid="p1",
        title="NIH R01 — Smith Lab",
        description="A grant project",
        owner_user_id="u1",
        team_id=None,
        state="active",
        root_folder_uuid="f1",
        kb_uuid="kb1",
        created_at=datetime.datetime(2026, 6, 15, 12, 0, 0),
        updated_at=datetime.datetime(2026, 6, 15, 12, 0, 0),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


CAPS = {
    "files": {"count": 3, "folders": 1},
    "knowledge": {"ready": True, "documents": 2},
    "workflows": {"count": 1},
    "extractions": {"count": 0},
    "automations": {"count": 0},
    "external_kbs": {"count": 0},
    "members": {"count": 1},
}


def test_serialize_project_shape():
    out = project_service.serialize_project(_project())
    assert out["uuid"] == "p1"
    assert out["title"] == "NIH R01 — Smith Lab"
    assert out["state"] == "active"
    # No capabilities/role on the bare serialization (create/update responses).
    assert "capabilities" not in out
    assert "role" not in out


@pytest.mark.asyncio
async def test_summarize_project_includes_role_and_capabilities():
    """List cards need the viewer's role (to gate manage actions) and the
    capability counts (to show what's inside) in one shot."""
    user = AsyncMock()
    with (
        patch.object(
            project_service, "get_project_capabilities",
            AsyncMock(return_value=CAPS),
        ),
        patch.object(
            project_service, "get_project_role",
            AsyncMock(return_value="owner"),
        ),
        patch.object(
            project_service, "_is_project_member",
            AsyncMock(return_value=False),
        ),
    ):
        out = await project_service.summarize_project(_project(), user)

    assert out["uuid"] == "p1"
    assert out["role"] == "owner"
    assert out["capabilities"] == CAPS
    assert out["can_leave"] is False


@pytest.mark.asyncio
async def test_overview_and_summary_share_capability_counts():
    """The project home (overview) and the list card must report the same
    'what's inside' numbers — both flow through get_project_capabilities."""
    user = AsyncMock()
    with (
        patch.object(
            project_service, "get_project_capabilities",
            AsyncMock(return_value=CAPS),
        ),
        patch.object(
            project_service, "get_project_role",
            AsyncMock(return_value="editor"),
        ),
        patch.object(
            project_service, "_is_project_member",
            AsyncMock(return_value=False),
        ),
    ):
        overview = await project_service.get_project_overview(_project(), user)
        summary = await project_service.summarize_project(_project(), user)

    assert overview["capabilities"] == summary["capabilities"] == CAPS
    assert overview["role"] == summary["role"] == "editor"


@pytest.mark.asyncio
async def test_duplicate_project_creates_personal_copy_and_copies_pins():
    """The shell copy is scoped to the caller (personal, "(Copy)" title) and
    duplicates the pin *references* — re-owned by the caller, targets intact."""
    source = _project(uuid="src", title="Grant A", description="desc",
                      team_id="teamX", state="closeout")
    user = SimpleNamespace(user_id="u2", current_team=None, is_admin=False)

    folders: list = []
    projects: list = []
    pins: list = []
    Folder = _fake_model(folders)
    Proj = _fake_model(projects)
    Pin = _fake_model(pins)
    # Source has two pins to copy; ProjectPin.find(...).to_list() returns them.
    src_pins = [
        SimpleNamespace(pin_type="workflow", target_id="w1"),
        SimpleNamespace(pin_type="knowledge_base", target_id="kb9"),
    ]
    Pin.find = _find_returning(src_pins)

    with (
        patch.object(project_service, "SmartFolder", Folder),
        patch.object(project_service, "Project", Proj),
        patch.object(project_service, "ProjectPin", Pin),
        patch("app.services.knowledge_service.create_knowledge_base",
              AsyncMock(return_value=SimpleNamespace(uuid="newkb"))),
    ):
        new = await project_service.duplicate_project(source, user)

    assert new.title == "Grant A (Copy)"
    assert new.owner_user_id == "u2"
    assert new.team_id is None          # personal, even though source was a team project
    assert new.state == "active"        # a duplicate is a fresh working copy
    assert new.description == "desc"
    assert new.kb_uuid == "newkb"
    # Root folder scoped to the caller.
    assert folders[0].user_id == "u2" and folders[0].team_id is None
    # Pins copied to the new project, re-owned, references unchanged.
    assert {(p.pin_type, p.target_id) for p in pins} == {("workflow", "w1"), ("knowledge_base", "kb9")}
    assert all(p.project_uuid == new.uuid and p.created_by == "u2" for p in pins)


@pytest.mark.asyncio
async def test_copy_project_contents_maps_subtree_and_enqueues_ingest():
    """Content copy recreates the folder subtree (parent links remapped), copies
    each document into the mapped folder with its own file, and enqueues
    semantic ingestion so the new project's implicit KB gets populated."""
    source = SimpleNamespace(uuid="src", root_folder_uuid="rootA")
    new = _fake_model([])(uuid="dst", root_folder_uuid="rootB",
                          updated_at=datetime.datetime(2026, 1, 1))

    folders: list = []
    docs: list = []
    Folder = _fake_model(folders)
    Doc = _fake_model(docs)
    Proj = _fake_model([])
    Proj.find_one = AsyncMock(side_effect=[source, new])
    # BFS: root's children = [childA]; childA's children = [] (stop).
    childA = SimpleNamespace(uuid="cA", parent_id="rootA", title="Sub")
    Folder.find = _find_returning([childA], [])
    # One document under childA to copy.
    src_doc = SimpleNamespace(
        uuid="dOLD", title="Budget.pdf", raw_text="hello world",
        text_markers=[], extension="pdf", downloadpath="u1/OLD.pdf", path="u1/OLD.pdf",
        folder="cA", token_count=5, num_pages=2, classification=None,
        classification_confidence=None, classified_at=None, classified_by=None, valid=True,
    )
    Doc.find = _find_returning([src_doc])

    storage = SimpleNamespace(read=AsyncMock(return_value=b"pdfbytes"), write=AsyncMock())
    ingest = MagicMock()

    with (
        patch.object(project_service, "SmartFolder", Folder),
        patch.object(project_service, "SmartDocument", Doc),
        patch.object(project_service, "Project", Proj),
        patch("app.services.storage.get_storage", return_value=storage),
        patch("app.tasks.document_tasks.perform_semantic_ingestion", ingest),
    ):
        result = await project_service.copy_project_contents("src", "dst", "u2")

    # rootA->rootB plus childA copied under rootB.
    assert result == {"folders": 2, "documents": 1}
    assert folders[0].parent_id == "rootB" and folders[0].user_id == "u2"
    new_child_uuid = folders[0].uuid
    # The document landed in the *mapped* new folder, re-owned, with its own file.
    assert docs[0].folder == new_child_uuid
    assert docs[0].user_id == "u2" and docs[0].team_id is None
    assert docs[0].raw_text == "hello world"
    assert docs[0].path == docs[0].downloadpath and docs[0].path != "u1/OLD.pdf"
    storage.read.assert_awaited_once_with("u1/OLD.pdf")
    storage.write.assert_awaited_once()
    # Ingestion enqueued for the new doc so its KB entry gets built.
    ingest.delay.assert_called_once()
    args = ingest.delay.call_args.args
    assert args[0] == "hello world" and args[2] == "u2"


@pytest.mark.asyncio
async def test_copy_project_contents_noops_when_project_missing():
    """A missing source/target project must not raise — just report zero work."""
    Proj = _fake_model([])
    Proj.find_one = AsyncMock(side_effect=[None, None])
    with patch.object(project_service, "Project", Proj):
        result = await project_service.copy_project_contents("nope", "nope2", "u2")
    assert result == {"folders": 0, "documents": 0}
