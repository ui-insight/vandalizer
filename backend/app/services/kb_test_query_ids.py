"""Human-readable IDs and provenance notes for auto-generated test queries.

An imported test set carries its own IDs (``KBTestQuery.external_id``) and
the importer preserves them as given, so a spreadsheet row can be tracked
across KB versions and validation runs. Auto-generated questions had no ID
at all, which left half of a mixed set untrackable: nothing to filter on,
nothing to cite in a review, nothing to line up between two runs' exports.

Every auto-generated question now gets ``<KB-prefix>-AUTO-Q<nnn>`` — e.g.
``FCOI-AUTO-Q007`` — where the prefix is derived from the KB title and the
number continues from the highest ``-AUTO-Q`` already on the KB, so
regenerating never reuses an ID. Imported IDs are never touched.

An ID is assigned once and never changes, but it is not deterministic: a
regenerated set gets fresh numbers. IDs are written on the write paths only
(generation and import); listing a KB's test queries never writes. A partial
unique index on ``(knowledge_base_uuid, external_id)`` is the final arbiter
between two concurrent writers, and ``dedupe_test_query_external_ids`` clears
any duplicates from before that index existed so it can be built at startup.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Awaitable, Callable, Iterable, Optional

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

AUTO_ID_SUFFIX_RE = re.compile(r"-AUTO-Q(\d+)$")

# A collision on write means another writer took the number between our
# re-check and our write; the next number is free with overwhelming
# likelihood. The cap only keeps a DuplicateKeyError on some *other* key
# from spinning forever.
_MAX_ID_COLLISION_RETRIES = 50

# Words that add nothing to a prefix: "FCOI Knowledge Base" should read as
# FCOI, not FKB.
_PREFIX_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "with",
    "kb", "knowledge", "base", "knowledgebase",
}
_MAX_SINGLE_WORD = 6
_MAX_INITIALS = 5


def kb_id_prefix(title: Optional[str], uuid: str = "") -> str:
    """Derive the short uppercase prefix for a KB's auto-generated query IDs.

    A one-word title keeps up to six characters of the word (``FCOI``,
    ``HANDBO``); a multi-word title takes the initials of up to five
    significant words (``Export Control Regulations`` → ``ECR``). A title
    that yields fewer than two characters falls back to ``KB`` plus the
    first four characters of the KB uuid, so the prefix is never empty and
    two such KBs still get distinct IDs.
    """
    words = re.findall(r"[A-Za-z0-9]+", title) if isinstance(title, str) else []
    significant = [w for w in words if w.lower() not in _PREFIX_STOPWORDS] or words
    # "2 CFR 200" should read as CFR, not 2C2: numerals only count when the
    # title has nothing else.
    significant = [w for w in significant if not w.isdigit()] or significant
    if len(significant) == 1:
        prefix = significant[0][:_MAX_SINGLE_WORD].upper()
    elif significant:
        prefix = "".join(w[0] for w in significant[:_MAX_INITIALS]).upper()
    else:
        prefix = ""
    if len(prefix) < 2:
        tail = re.sub(r"[^A-Za-z0-9]", "", uuid or "")[:4].upper()
        prefix = f"KB{tail}"
    return prefix


def auto_query_id(prefix: str, number: int) -> str:
    return f"{prefix}-AUTO-Q{number:03d}"


def next_auto_query_number(existing_ids: Iterable[Optional[str]]) -> int:
    """One past the highest ``-AUTO-Q<n>`` among ``existing_ids``, else 1.

    Any prefix counts: a KB renamed between two generations changes the
    prefix, and continuing the count anyway keeps the sequence unique.
    """
    highest = 0
    for eid in existing_ids:
        m = AUTO_ID_SUFFIX_RE.search(eid or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


class AutoQueryIdAllocator:
    """Hands out consecutive auto IDs continuing past everything on the KB.

    ``allocate`` is pure: it continues from the IDs it was given. ``reserve``
    re-checks the KB before handing an ID out, so two writers that read the
    same IDs (a generation racing another generation, a backfill, or an
    import) do not usually mint the same number. The unique index on
    ``(knowledge_base_uuid, external_id)`` catches the race the re-check
    cannot see; ``reserve_and_write`` turns that into "take the next number".
    """

    def __init__(self, prefix: str, existing_ids: Iterable[Optional[str]]):
        self.prefix = prefix
        self._next = next_auto_query_number(existing_ids)

    def allocate(self) -> str:
        candidate = auto_query_id(self.prefix, self._next)
        self._next += 1
        return candidate

    async def reserve(self, kb_uuid: str, *, exclude_uuid: Optional[str] = None) -> str:
        """The next ID no *other* row on the KB holds right now.

        ``exclude_uuid`` is the row about to receive the ID: a backfill that
        re-runs concurrently assigns the same IDs to the same rows, and its
        own earlier write must not read as a collision.
        """
        from app.models.kb_test_query import KBTestQuery

        while True:
            candidate = self.allocate()
            query: dict = {"knowledge_base_uuid": kb_uuid, "external_id": candidate}
            if exclude_uuid:
                query["uuid"] = {"$ne": exclude_uuid}
            if await KBTestQuery.find_one(query) is None:
                return candidate


async def reserve_and_write(
    allocator: AutoQueryIdAllocator,
    row,
    kb_uuid: str,
    *,
    write: Callable[[], Awaitable[object]],
    exclude_uuid: Optional[str] = None,
) -> str:
    """Put a reserved ID on ``row`` and persist it with ``write``.

    ``write`` is the row's own ``insert`` (a new generated question) or
    ``save`` (a backfilled legacy one). When the unique index rejects the
    write because another writer took the same number between our re-check
    and our write, the next number is reserved and the write retried, so a
    racing generation and import both finish with distinct IDs instead of
    one of them failing. Returns the ID that was written.
    """
    for _ in range(_MAX_ID_COLLISION_RETRIES):
        row.external_id = await allocator.reserve(kb_uuid, exclude_uuid=exclude_uuid)
        try:
            await write()
        except DuplicateKeyError:
            logger.info(
                "Auto query ID %s on KB %s was taken between reserve and write; "
                "retrying with the next number",
                row.external_id, kb_uuid,
            )
            continue
        return row.external_id
    raise RuntimeError(
        f"Could not find a free auto query ID on KB {kb_uuid} after "
        f"{_MAX_ID_COLLISION_RETRIES} collisions"
    )


def auto_query_notes(
    *,
    source_names: Iterable[str],
    coverage: str,
    model_name: Optional[str],
    generated_at: Optional[datetime.datetime] = None,
) -> str:
    """Provenance note for an auto-generated question, in the Notes column.

    Reads like the note an evaluator would write for an imported row: when
    it was made, from which source(s), at what coverage, by which model.
    """
    when = (generated_at or datetime.datetime.now(tz=datetime.timezone.utc)).date().isoformat()
    names = [n for n in dict.fromkeys(s.strip() for s in source_names if s) if n]
    origin = f" from {', '.join(names)}" if names else ""
    model = f", model {model_name}" if model_name else ""
    return f"Auto-generated {when}{origin} ({coverage} coverage{model})."


async def backfill_auto_query_ids(kb) -> int:
    """Give IDs to a KB's auto-generated queries that predate this scheme.

    Runs on the write paths only — before a generation allocates its batch,
    so legacy rows are numbered first and the new questions continue after
    them, and before an import. Listing never calls it, so a read-only
    member's page view writes nothing; a KB nobody generates or imports on
    again simply shows no ID on its older rows.

    Deterministic — oldest first, continuing from the highest existing
    number — so two concurrent callers assign the same IDs to the same rows;
    an ID a concurrent generation took in the meantime is skipped.
    Returns how many rows were updated. Imported and hand-written queries
    are left exactly as they are.
    """
    from app.models.kb_test_query import KBTestQuery

    queries = await KBTestQuery.find(
        KBTestQuery.knowledge_base_uuid == kb.uuid,
    ).to_list()
    missing = [q for q in queries if q.auto_generated and not getattr(q, "external_id", None)]
    if not missing:
        return 0
    allocator = AutoQueryIdAllocator(
        kb_id_prefix(getattr(kb, "title", None), kb.uuid),
        (getattr(q, "external_id", None) for q in queries),
    )
    missing.sort(key=lambda q: (q.created_at or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), q.uuid))
    for q in missing:
        await reserve_and_write(allocator, q, kb.uuid, write=q.save, exclude_uuid=q.uuid)
    return len(missing)


def _dedupe_sort_key(row: dict) -> tuple:
    """Oldest first: by ``created_at`` when present, then by ObjectId (which
    embeds its own creation time). Naive and aware datetimes are both reduced
    to a timestamp so a mixed collection cannot raise on comparison."""
    created = row.get("created_at")
    return (
        created is None,
        created.timestamp() if isinstance(created, datetime.datetime) else 0.0,
        str(row.get("_id")),
    )


async def dedupe_test_query_external_ids(collection) -> int:
    """Clear ``external_id`` on all but the oldest row of each duplicated
    ``(knowledge_base_uuid, external_id)`` pair.

    Runs before Beanie builds the partial unique index on that pair: building
    a unique index over data that already contains duplicates fails, and a
    failed index build at init would crash every process at startup. The
    oldest row keeps the ID — it is the one earlier validation runs and
    exports cited — and each cleared row is logged with its KB, the ID, and
    the affected query uuids so an operator can re-import or regenerate.
    ``collection`` is the raw Motor collection, because this runs before the
    ODM is initialised. Returns the number of rows whose ID was cleared.
    """
    pipeline = [
        {"$match": {"external_id": {"$type": "string"}}},
        {"$group": {
            "_id": {"kb": "$knowledge_base_uuid", "external_id": "$external_id"},
            "rows": {"$push": {"_id": "$_id", "uuid": "$uuid", "created_at": "$created_at"}},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    cleared = 0
    async for group in collection.aggregate(pipeline):
        rows = sorted(group["rows"], key=_dedupe_sort_key)
        keep, losers = rows[0], rows[1:]
        await collection.update_many(
            {"_id": {"$in": [r["_id"] for r in losers]}},
            {"$set": {"external_id": None}},
        )
        logger.warning(
            "KB %s: test-query ID %r was on %d rows; kept it on query %s and "
            "cleared it from %s so the unique index can be built",
            group["_id"]["kb"], group["_id"]["external_id"], len(rows),
            keep.get("uuid"), [r.get("uuid") for r in losers],
        )
        cleared += len(losers)
    return cleared
