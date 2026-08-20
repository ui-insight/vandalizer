"""Tests for the orphaned-workflow cleanup script's decision rule.

The script itself needs a live MongoDB, so the fetching is thin and the rule
that decides which workflows are stranded is pure and tested here. Getting
this rule wrong is expensive in both directions: too loose and it re-bookmarks
workflows that were reachable all along, too strict and the names stay blocked.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId

from scripts.adopt_orphaned_workflows import (
    bookmarked_workflow_ids,
    is_orphan,
    referenced_workflow_ids,
)


def _library(items):
    return SimpleNamespace(items=items)


def _item(target_id):
    return SimpleNamespace(id=PydanticObjectId(), item_id=target_id)


class TestBookmarkedWorkflowIds:
    def test_counts_a_row_a_library_actually_lists(self):
        wf_id = PydanticObjectId()
        item = _item(wf_id)

        assert bookmarked_workflow_ids([_library([item.id])], [item]) == {wf_id}

    def test_ignores_a_row_no_library_lists(self):
        # Exactly what the old Library delete left behind. Such a row renders
        # in no listing, so treating it as a bookmark would leave the workflow
        # invisible and its name blocked — the bug this script repairs.
        wf_id = PydanticObjectId()
        item = _item(wf_id)

        assert bookmarked_workflow_ids([_library([])], [item]) == set()

    def test_a_bookmark_in_any_library_counts(self):
        # Shared to a team and removed from the owner's personal library: still
        # reachable, still not an orphan.
        wf_id = PydanticObjectId()
        item = _item(wf_id)
        personal, team = _library([]), _library([item.id])

        assert bookmarked_workflow_ids([personal, team], [item]) == {wf_id}


class TestReferencedWorkflowIds:
    def test_collects_automations_pins_and_verified_metadata(self):
        a, b, c = (str(PydanticObjectId()) for _ in range(3))

        result = referenced_workflow_ids(
            [SimpleNamespace(action_id=a)],
            [SimpleNamespace(target_id=b)],
            [SimpleNamespace(item_id=c)],
        )

        assert result == {a, b, c}

    def test_skips_an_automation_with_no_action_yet(self):
        # A half-configured automation points at nothing; it must not pull an
        # unrelated workflow out of the cleanup.
        assert referenced_workflow_ids([SimpleNamespace(action_id=None)], [], []) == set()


class TestIsOrphan:
    def test_unbookmarked_and_unreferenced_is_an_orphan(self):
        wf = SimpleNamespace(id=PydanticObjectId())

        assert is_orphan(wf, set(), set()) is True

    def test_bookmarked_is_not_an_orphan(self):
        wf = SimpleNamespace(id=PydanticObjectId())

        assert is_orphan(wf, {wf.id}, set()) is False

    def test_referenced_by_another_surface_is_not_an_orphan(self):
        # An automation's action or a project pin keeps a workflow reachable
        # and manageable from that surface even with no library bookmark.
        wf = SimpleNamespace(id=PydanticObjectId())

        assert is_orphan(wf, set(), {str(wf.id)}) is False

    def test_reference_ids_are_matched_as_strings_not_object_ids(self):
        # Regression guard on the two id representations the script juggles:
        # bookmarks come back as PydanticObjectId (Workflow.id), while
        # automations, pins and verified metadata store the id as a string.
        # Comparing the wrong pair silently matches nothing, which would adopt
        # workflows that a live automation still runs.
        wf = SimpleNamespace(id=PydanticObjectId())

        assert is_orphan(wf, set(), {wf.id}) is True
        assert is_orphan(wf, set(), {str(wf.id)}) is False


# ---------------------------------------------------------------------------
# adopt(): the run must be safe to interrupt, and safe to run concurrently
# ---------------------------------------------------------------------------

class _Cursor:
    """An async cursor that records whether it has been fully consumed."""

    def __init__(self, items):
        self._items = list(items)
        self.exhausted = False

    def __aiter__(self):
        async def gen():
            for it in self._items:
                yield it
            self.exhausted = True
        return gen()


def _wf(name, wid, owner="alice"):
    return SimpleNamespace(
        id=PydanticObjectId(),
        name=name,
        user_id=owner,
        created_by_user_id=owner,
        verified=False,
        created_at=None,
    )


async def _run_adopt(monkeypatch, workflows, *, dry_run=False):
    """Drive adopt() against stand-in models, returning what it wrote."""
    import scripts.adopt_orphaned_workflows as mod

    cursor = _Cursor(workflows)
    inserted_during_scan: list[bool] = []
    updates: list[tuple] = []

    monkeypatch.setattr(mod, "AsyncIOMotorClient", lambda *a, **k: {"db": MagicMock()})
    monkeypatch.setattr(mod, "init_beanie", AsyncMock())
    monkeypatch.setattr(mod, "Settings", lambda: SimpleNamespace(mongo_host="", mongo_db="db"))
    monkeypatch.setattr(mod, "_fetch_bookmarked", AsyncMock(return_value=set()))
    monkeypatch.setattr(mod, "_fetch_referenced", AsyncMock(return_value=set()))

    workflow_cls = MagicMock()
    workflow_cls.find = MagicMock(return_value=cursor)
    monkeypatch.setattr(mod, "Workflow", workflow_cls)

    class _LibraryItem:
        def __init__(self, **kw):
            self.id = PydanticObjectId()
            self.__dict__.update(kw)

        async def insert(self):
            # Records whether the scan cursor was still open at write time.
            inserted_during_scan.append(not cursor.exhausted)

    monkeypatch.setattr(mod, "LibraryItem", _LibraryItem)

    coll = MagicMock()
    coll.update_one = AsyncMock(side_effect=lambda q, u: updates.append((q, u)))
    library_cls = MagicMock()
    library_cls.get_motor_collection = MagicMock(return_value=coll)
    monkeypatch.setattr(mod, "Library", library_cls)
    monkeypatch.setattr(
        mod, "_personal_library",
        AsyncMock(side_effect=lambda owner, cache: SimpleNamespace(id=f"lib-{owner}")),
    )

    stats = await mod.adopt(dry_run=dry_run)
    return stats, inserted_during_scan, updates


@pytest.mark.asyncio
async def test_nothing_is_written_while_the_scan_cursor_is_open(monkeypatch):
    """Writing inside the cursor loop held it open across every insert.

    A ten-minute cursor expiry, a crash, or a Ctrl-C then left LibraryItem rows
    that no library referenced — invisible, and re-running inserted a second set
    rather than reusing them, so every attempt added more garbage. That is
    precisely the state this script exists to repair.
    """
    stats, inserted_during_scan, _updates = await _run_adopt(
        monkeypatch, [_wf("A", 1), _wf("B", 2)],
    )

    assert stats["adopted"] == 2
    assert inserted_during_scan and not any(inserted_during_scan), (
        "a LibraryItem was inserted while the scan cursor was still open"
    )


@pytest.mark.asyncio
async def test_the_library_is_appended_to_rather_than_overwritten(monkeypatch):
    """lib.items.extend(...) + save() writes the whole array from a snapshot
    read when the library was first fetched, so a bookmark the owner made while
    the script ran was silently overwritten away — creating a fresh orphan of
    exactly the kind being repaired."""
    _stats, _during, updates = await _run_adopt(monkeypatch, [_wf("A", 1)])

    assert len(updates) == 1
    _query, update = updates[0]
    assert "$push" in update, "the whole items array was rewritten"
    assert "$each" in update["$push"]["items"]
    assert "items" not in update.get("$set", {}), (
        "items was $set, which clobbers concurrent bookmarks"
    )


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_at_all(monkeypatch):
    stats, inserted, updates = await _run_adopt(
        monkeypatch, [_wf("A", 1)], dry_run=True,
    )
    assert stats["adopted"] == 1
    assert inserted == []
    assert updates == []
