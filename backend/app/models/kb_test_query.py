"""KBTestQuery model - test queries for knowledge base validation."""

import datetime
from typing import Optional
from uuid import uuid4

import pymongo
from beanie import Document
from pydantic import Field

# Name is pinned so the pre-init dedup and any operator looking at
# ``db.kb_test_queries.getIndexes()`` can refer to it.
KB_TEST_QUERY_EXTERNAL_ID_UNIQUE_INDEX = "kb_test_queries_kb_external_id_unique"


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
    # Free-text evaluator notes (rationale, provenance, caveats).
    notes: Optional[str] = None
    # Stable caller-supplied identifier carried in from bulk imports;
    # re-importing a spreadsheet updates the matching row instead of
    # duplicating it, so a test set can track a KB across versions.
    external_id: Optional[str] = None
    # The bulk import that last wrote this row (created or updated it). Lets
    # an evaluator pick out "the set I just imported" from the combined list
    # and validate it in isolation. None for manual and generated rows.
    import_batch_id: Optional[str] = None
    import_batch_label: Optional[str] = None
    import_batch_at: Optional[datetime.datetime] = None
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
        indexes = [
            "uuid",
            "knowledge_base_uuid",
            # An ID is unique within its KB. Partial on string-typed IDs so
            # the many rows with external_id=None/missing do not collide.
            # Two writers that both pass the allocator's re-check meet here;
            # the loser retries with the next number (kb_test_query_ids).
            # ``database._run_pre_index_migrations`` clears pre-existing
            # duplicates before Beanie builds this, or init would fail.
            pymongo.IndexModel(
                [("knowledge_base_uuid", pymongo.ASCENDING), ("external_id", pymongo.ASCENDING)],
                name=KB_TEST_QUERY_EXTERNAL_ID_UNIQUE_INDEX,
                unique=True,
                partialFilterExpression={"external_id": {"$type": "string"}},
            ),
        ]

    def __init__(self, **data):
        super().__init__(**data)
        if not self.uuid:
            self.uuid = uuid4().hex
