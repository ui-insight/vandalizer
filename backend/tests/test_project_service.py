"""Tests for project_service serialization — the list/overview shapes the
explorer cards and project home depend on."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import project_service


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
    ):
        out = await project_service.summarize_project(_project(), user)

    assert out["uuid"] == "p1"
    assert out["role"] == "owner"
    assert out["capabilities"] == CAPS


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
    ):
        overview = await project_service.get_project_overview(_project(), user)
        summary = await project_service.summarize_project(_project(), user)

    assert overview["capabilities"] == summary["capabilities"] == CAPS
    assert overview["role"] == summary["role"] == "editor"
