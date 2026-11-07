from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import chat_file_tools as tools


@pytest.fixture
def setup(monkeypatch):
    project = SimpleNamespace(uuid="project", title="Subaward", root_folder_uuid="destination")
    folder = SimpleNamespace(uuid="destination", team_id=None)
    docs = {uuid: SimpleNamespace(uuid=uuid, title=f"{uuid}.pdf", folder="source", team_id=None) for uuid in ["award", "budget"]}
    conv = SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    ctx = SimpleNamespace(deps=SimpleNamespace(user=object(), active_project_uuid="project", context_document_uuids=["award"], conversation=conv, turn_marker=1))
    get_project = AsyncMock(return_value=project)
    get_folder = AsyncMock(return_value=folder)
    get_doc = AsyncMock(side_effect=lambda uuid, *args, **kwargs: docs.get(uuid))
    move = AsyncMock(return_value=True)
    monkeypatch.setattr(tools.project_service, "get_authorized_project", get_project)
    monkeypatch.setattr(tools.access_control, "get_authorized_folder", get_folder)
    monkeypatch.setattr(tools.access_control, "get_authorized_document", get_doc)
    monkeypatch.setattr(tools.file_service, "move_document", move)
    return SimpleNamespace(ctx=ctx, project=project, folder=folder, docs=docs, move=move, get_project=get_project, get_folder=get_folder, get_doc=get_doc)


async def test_attached_file_moves_only_after_prior_turn_approval(setup):
    result = await tools.move_documents_to_project(setup.ctx, confirmed=True)
    assert result["needs_confirmation"] is True
    assert "award.pdf" in result["preview"] and "Subaward" in result["preview"]
    assert "leave their current folders" in result["preview"]
    assert result["approval_label"] == "Move files"
    setup.move.assert_not_awaited()
    assert (await tools.move_documents_to_project(setup.ctx, confirmed=True))["needs_confirmation"]
    setup.ctx.deps.turn_marker = 2
    result = await tools.move_documents_to_project(setup.ctx, confirmed=True)
    assert result["status"] == "completed"
    assert result["moved_documents"] == [{"uuid": "award", "title": "award.pdf"}]
    setup.move.assert_awaited_once_with("award", "destination", user=setup.ctx.deps.user)
    setup.get_doc.assert_awaited_with("award", setup.ctx.deps.user, manage=True)
    setup.get_folder.assert_awaited_with("destination", setup.ctx.deps.user, contribute=True)


@pytest.mark.parametrize("change", ["selection", "source", "destination"])
async def test_changed_move_needs_new_approval(setup, change):
    await tools.move_documents_to_project(setup.ctx)
    setup.ctx.deps.turn_marker = 2
    if change == "selection":
        setup.ctx.deps.context_document_uuids = ["budget"]
    elif change == "source":
        setup.docs["award"].folder = "different-folder"
    else:
        setup.folder.uuid = "other-destination"
    result = await tools.move_documents_to_project(setup.ctx, confirmed=True)
    assert result["needs_confirmation"]
    setup.move.assert_not_awaited()


@pytest.mark.parametrize("denied", ["project", "destination", "source", "team"])
async def test_permissions_rechecked_after_approval_and_no_partial_preflight_writes(setup, denied):
    await tools.move_documents_to_project(setup.ctx, document_uuids=["award", "budget"])
    setup.ctx.deps.turn_marker = 2
    if denied == "project":
        setup.get_project.return_value = None
    elif denied == "destination":
        setup.get_folder.return_value = None
    elif denied == "source":
        setup.docs.pop("budget")
    else:
        setup.docs["budget"].team_id = "other-team"
    result = await tools.move_documents_to_project(setup.ctx, document_uuids=["award", "budget"], confirmed=True)
    assert "error" in result
    setup.move.assert_not_awaited()


async def test_explicit_project_works_without_opening_it_and_reports_partial_failure(setup):
    setup.ctx.deps.active_project_uuid = None
    await tools.move_documents_to_project(setup.ctx, "project", ["award", "budget", "award"])
    setup.ctx.deps.turn_marker = 2
    setup.move.side_effect = [True, False]
    result = await tools.move_documents_to_project(setup.ctx, "project", ["award", "budget", "award"], True)
    assert result["status"] == "partial"
    assert len(result["moved_documents"]) == 1
    assert result["failed_documents"][0]["uuid"] == "budget"
    assert setup.move.await_count == 2


async def test_already_in_destination_does_not_move_or_duplicate(setup):
    setup.docs["award"].folder = "destination"
    result = await tools.move_documents_to_project(setup.ctx)
    assert result["already_in_project"][0]["uuid"] == "award"
    assert result["moved_documents"] == []
    setup.move.assert_not_awaited()


async def test_project_discovery_uses_authorized_listing(setup, monkeypatch):
    listing = AsyncMock(return_value=[setup.project])
    monkeypatch.setattr(tools.project_service, "list_projects", listing)
    assert (await tools.list_projects(setup.ctx, "SUBAWARD"))[0]["uuid"] == "project"
    assert await tools.list_projects(setup.ctx, "unrelated") == []
    listing.assert_awaited_with(setup.ctx.deps.user)


def test_moves_are_registered_as_sequential_noncompactable_writes():
    from app.services.chat_tools import TOOLS, COMPACTABLE_TOOLS, PARALLEL_SAFE_TOOLS
    assert tools.move_documents_to_project in TOOLS
    assert tools.list_projects in TOOLS
    assert "move_documents_to_project" not in COMPACTABLE_TOOLS | PARALLEL_SAFE_TOOLS
