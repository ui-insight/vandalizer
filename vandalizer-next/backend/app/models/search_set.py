"""SearchSet and SearchSetItem models matching existing MongoDB collections."""

import datetime
from typing import Optional

from beanie import Document


class SearchSetItem(Document):
    """Represents an extraction item."""

    searchphrase: str
    searchset: Optional[str] = None
    searchtype: str
    text_blocks: list[str] = []
    pdf_binding: Optional[str] = None
    user_id: Optional[str] = None
    space_id: Optional[str] = None
    title: Optional[str] = None

    class Settings:
        name = "search_set_item"


class SearchSet(Document):
    """Represents an extraction set."""

    title: str
    uuid: str
    space: str
    status: str
    set_type: str
    user_id: Optional[str] = None
    is_global: bool = False
    created_at: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    user: Optional[str] = None
    fillable_pdf_url: Optional[str] = None
    verified: bool = False
    created_by_user_id: Optional[str] = None
    extraction_config: dict = {}

    class Settings:
        name = "search_set"

    async def get_items(self) -> list[SearchSetItem]:
        return await SearchSetItem.find(SearchSetItem.searchset == self.uuid).to_list()

    async def get_extraction_items(self) -> list[SearchSetItem]:
        return await SearchSetItem.find(
            SearchSetItem.searchset == self.uuid,
            SearchSetItem.searchtype == "extraction",
        ).to_list()

    async def item_count(self) -> int:
        return await SearchSetItem.find(
            SearchSetItem.searchset == self.uuid
        ).count()
