"""Library responses carry a Skill's "When to use" line (support ticket).

``LibraryItemResponse`` had no ``when_to_use`` field, so the line the service
resolved was dropped from every Library response. Edit Skill opened with the
field empty and Update saved it empty, pausing the Skill as a core Skill.
"""

from unittest.mock import AsyncMock

import pytest

from app.routers import library as routes
from app.schemas.library import LibraryItemResponse

ITEM = {
    "id": "li-1", "item_id": "ss-1", "item_uuid": "ss-uuid-1", "kind": "search_set",
    "name": "Budget summary style", "description": None, "set_type": "prompt",
    "when_to_use": "Summarizing a budget justification", "tags": [], "note": None, "folder": None,
    "pinned": False, "favorited": False, "verified": False, "added_by_user_id": "u",
}


def test_the_item_response_keeps_the_line():
    assert LibraryItemResponse(**ITEM).model_dump()["when_to_use"] == "Summarizing a budget justification"
    assert LibraryItemResponse(**{**ITEM, "when_to_use": None}).when_to_use is None


@pytest.mark.asyncio
async def test_the_library_list_returns_the_line(monkeypatch):
    """The list Edit Skill opens from: GET /api/library/{id}/items."""
    from types import SimpleNamespace

    monkeypatch.setattr(routes.Library, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.svc, "get_library_items", AsyncMock(return_value=[ITEM]))
    items = await routes.list_items("0123456789abcdef01234567", kind=None, folder=None, search=None,
                                    user=SimpleNamespace(user_id="u"))
    assert items[0].model_dump()["when_to_use"] == "Summarizing a budget justification"
