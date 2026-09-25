"""POST /api/documents/titles — resolves a chat setup link's documents and folders.

Only what the caller can view comes back; the rest is dropped silently so the
response reveals nothing about documents that weren't shared with them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import documents as router

USER = SimpleNamespace(user_id="bob")
VISIBLE_DOCS = {"doc-1": "2 CFR 200 Subpart E.pdf", "doc-2": None}
VISIBLE_FOLDERS = {"fld-1": "Travel"}


async def _doc(uuid, user, **kw):
    if uuid in VISIBLE_DOCS:
        return SimpleNamespace(uuid=uuid, title=VISIBLE_DOCS[uuid])
    return None


async def _folder(uuid, user, **kw):
    if uuid in VISIBLE_FOLDERS:
        return SimpleNamespace(uuid=uuid, title=VISIBLE_FOLDERS[uuid])
    return None


def _patched():
    ac = router.access_control
    return (
        patch.object(ac, "get_team_access_context", AsyncMock(return_value=None)),
        patch.object(ac, "get_authorized_document", AsyncMock(side_effect=_doc)),
        patch.object(ac, "get_authorized_folder", AsyncMock(side_effect=_folder)),
    )


async def test_returns_only_what_the_caller_can_view():
    a, b, c = _patched()
    with a, b, c:
        out = await router.resolve_titles(
            router.TitlesRequest(
                document_uuids=["doc-1", "secret", "doc-2", "doc-1"],
                folder_uuids=["fld-1", "hidden"],
            ),
            user=USER,
        )
    assert out == {
        "documents": [
            {"uuid": "doc-1", "title": "2 CFR 200 Subpart E.pdf"},
            # An untitled document falls back to its uuid, as the chat route does.
            {"uuid": "doc-2", "title": "doc-2"},
        ],
        "folders": [{"uuid": "fld-1", "title": "Travel"}],
    }


async def test_checks_access_the_way_the_chat_route_does():
    a, b, c = _patched()
    with a, b as get_doc, c:
        await router.resolve_titles(router.TitlesRequest(document_uuids=["doc-1"]), user=USER)
    assert get_doc.await_args.kwargs["allow_admin"] is True
    assert "manage" not in get_doc.await_args.kwargs


async def test_refuses_an_oversized_lookup():
    with pytest.raises(HTTPException) as exc:
        await router.resolve_titles(
            router.TitlesRequest(document_uuids=[f"d{i}" for i in range(101)]), user=USER,
        )
    assert exc.value.status_code == 400
