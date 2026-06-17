"""KBTestQuery model - test queries for knowledge base validation."""

import datetime
from typing import Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field


class KBTestQuery(Document):
    """A sample query used to validate knowledge base retrieval quality."""

    uuid: str = ""
    knowledge_base_uuid: str
    query: str
    expected_source_labels: list[str] = Field(default_factory=list)
    expected_answer_contains: Optional[str] = None
    expected_answer: Optional[str] = None
    auto_generated: bool = False
    category: Optional[str] = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    last_judged_score: Optional[float] = None
    last_judged_at: Optional[datetime.datetime] = None
    user_id: str
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    # Set when a user edits the query/expected answer after creation; None for
    # records that have never been edited.
    updated_at: Optional[datetime.datetime] = None

    class Settings:
        name = "kb_test_queries"
        indexes = ["uuid", "knowledge_base_uuid"]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
