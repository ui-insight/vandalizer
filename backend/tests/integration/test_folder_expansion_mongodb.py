"""Tier 2: expanding ticked folders to documents (workflow runs, "Add folder
to knowledge base") skips superseded versions and soft-deleted documents,
against a real MongoDB so the query, not a stand-in, is what's tested."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_expansion_returns_current_live_documents_only(mongo_client):
    from app.models.document import SmartDocument
    from app.models.folder import SmartFolder
    from app.services import folder_service

    tag = uuid4().hex[:8]
    root, child = f"root-{tag}", f"child-{tag}"
    await SmartFolder(uuid=root, parent_id="0", title="Awards", user_id="u1").insert()
    await SmartFolder(uuid=child, parent_id=root, title="Subawards", user_id="u1").insert()

    async def doc(name: str, folder: str, **fields) -> str:
        uuid = f"{name}-{tag}"
        await SmartDocument(uuid=uuid, title=f"{name}.pdf", path="x", downloadpath="x",
                            user_id="u1", folder=folder, **fields).insert()
        return uuid

    plain = await doc("plain", root)
    await doc("v1", root, superseded_by=f"v2-{tag}")
    v2 = await doc("v2", root, version_number=2)
    await doc("deleted", child, soft_deleted=True)
    nested = await doc("nested", child)

    with patch.object(folder_service.access_control, "get_team_access_context", AsyncMock(return_value=MagicMock())), \
         patch.object(folder_service.access_control, "get_authorized_folder", AsyncMock(return_value=MagicMock(uuid=root))), \
         patch.object(folder_service.access_control, "get_authorized_document", AsyncMock(return_value=True)):
        result = await folder_service.expand_folders_to_document_uuids([root], MagicMock(user_id="u1"))

    assert sorted(result) == sorted([plain, v2, nested])
