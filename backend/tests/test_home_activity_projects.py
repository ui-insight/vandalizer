"""Home continuation rows name their project (#1014 item 30)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.config import _activity_project_titles


@pytest.mark.asyncio
async def test_names_only_projects_the_viewer_can_open():
    projects = {"p-open": SimpleNamespace(title="NSF CAREER 2027"), "p-gone": None}
    lookup = AsyncMock(side_effect=lambda uuid, user: projects[uuid])
    events = [
        SimpleNamespace(project_uuid="p-open"),
        SimpleNamespace(project_uuid="p-open"),
        SimpleNamespace(project_uuid="p-gone"),
        SimpleNamespace(project_uuid=None),
        SimpleNamespace(),  # an event written before the field existed
    ]
    with patch("app.services.project_service.get_authorized_project", lookup):
        titles = await _activity_project_titles(events, MagicMock())
    assert titles == {"p-open": "NSF CAREER 2027"}
    assert lookup.await_count == 2  # each project looked up once


@pytest.mark.asyncio
async def test_a_failed_lookup_leaves_the_row_unnamed():
    with patch(
        "app.services.project_service.get_authorized_project",
        AsyncMock(side_effect=RuntimeError("db")),
    ):
        assert await _activity_project_titles([SimpleNamespace(project_uuid="p")], MagicMock()) == {}
