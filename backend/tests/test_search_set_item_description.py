"""An extraction field's description is saved, cleared, and copied (#1057)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import search_set_service as svc

OID = "5f0000000000000000000001"


def _item(description=None):
    item = SimpleNamespace(searchphrase="Total Direct Costs", title=None, is_optional=False,
                           enum_values=[], description=description)
    item.save = AsyncMock()
    return item


@pytest.mark.asyncio
async def test_update_saves_a_trimmed_description():
    item = _item()
    with patch.object(svc.SearchSetItem, "get", AsyncMock(return_value=item)):
        await svc.update_item(OID, description="  Also labelled TDC.  ")
    assert item.description == "Also labelled TDC."


@pytest.mark.asyncio
async def test_an_empty_description_clears_it_and_omitting_it_keeps_it():
    item = _item("old")
    with patch.object(svc.SearchSetItem, "get", AsyncMock(return_value=item)):
        await svc.update_item(OID, is_optional=True)
        assert item.description == "old"
        await svc.update_item(OID, description="")
    assert item.description is None


@pytest.mark.asyncio
async def test_field_metadata_carries_the_description():
    items = [SimpleNamespace(searchphrase="Total Direct Costs", is_optional=False,
                             enum_values=[], description="Also labelled TDC.")]
    model = MagicMock()
    model.find.return_value.to_list = AsyncMock(return_value=items)
    with patch.object(svc, "SearchSetItem", model):
        meta = await svc.get_extraction_field_metadata("ss-1")
    assert meta == [{"key": "Total Direct Costs", "is_optional": False, "enum_values": [], "description": "Also labelled TDC."}]
