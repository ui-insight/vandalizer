"""One-shot cleanup: re-attach workflows that lost their library bookmark.

Workflows and extractions are only ever listed through library bookmarks, so
a workflow with no bookmark is invisible in every UI surface — while
``name_conflicts`` still counts it, so its name stays reserved. Users hit this
as "I deleted that workflow but I still can't reuse the name", with nowhere in
the app to go and look.

Two things produced these orphans:

* The old Library delete removed only the bookmark and left the workflow
  behind. ``remove_item(delete_underlying=True)`` now cascades instead.
* Duplicate / import / catalog-import created the workflow and left the
  bookmark to a second call from the client, which only the library's own
  modal ever made. Those paths now call ``library_service.ensure_bookmark``.

Both holes are closed going forward; this repairs the workflows already
stranded. Each orphan gets a bookmark in its owner's personal library, so it
becomes visible and the owner can rename or delete it themselves. Nothing is
deleted here — a workflow the user quietly built real work in is worth more
than the name it holds, and only the owner can judge which one this is.

A workflow is left alone when anything else still points at it — an
automation's action, a project pin, or verified-catalog metadata — because
those are reachable through their own surfaces and are not orphans.

Idempotent: a workflow that already has a bookmark is skipped, so re-running
after a partial run is safe.

Usage:
    uv run python -m scripts.adopt_orphaned_workflows              # apply
    uv run python -m scripts.adopt_orphaned_workflows --dry-run    # report only
    uv run python -m scripts.adopt_orphaned_workflows --user <id>  # one owner
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from collections import defaultdict

from beanie import PydanticObjectId, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.automation import Automation
from app.models.library import Library, LibraryItem, LibraryItemKind, LibraryScope
from app.models.project import ProjectPin
from app.models.verification import VerifiedItemMetadata
from app.models.workflow import Workflow


def bookmarked_workflow_ids(libraries, workflow_items) -> set[PydanticObjectId]:
    """Workflow ids reachable from some library's item list.

    A ``LibraryItem`` row that no ``Library.items`` array references renders
    nowhere, so it does not count as a bookmark — mirrors
    ``library_service.has_bookmark``. Pure so the orphan rule can be tested
    without a database; the caller does the fetching.

    Returns ``PydanticObjectId``, matching ``Workflow.id``. Compare against
    :func:`referenced_workflow_ids` — which returns strings, because the
    referring fields store ids as strings — only after converting.
    """
    live_item_ids: set[PydanticObjectId] = set()
    for lib in libraries:
        live_item_ids.update(lib.items)
    return {
        item.item_id for item in workflow_items if item.id in live_item_ids
    }


def referenced_workflow_ids(automations, pins, verified_metadata) -> set[str]:
    """Workflow ids some non-library surface still points at.

    These are reachable and manageable from that surface, so they are not
    orphans even without a bookmark. All three sources store the id as a
    string, so this returns strings.
    """
    referenced: set[str] = set()
    for auto in automations:
        if auto.action_id:
            referenced.add(str(auto.action_id))
    for pin in pins:
        referenced.add(str(pin.target_id))
    for meta in verified_metadata:
        referenced.add(str(meta.item_id))
    return referenced


def is_orphan(
    workflow, bookmarked: set[PydanticObjectId], referenced: set[str]
) -> bool:
    """True when nothing in the app can reach *workflow* any more."""
    return workflow.id not in bookmarked and str(workflow.id) not in referenced


async def _fetch_bookmarked() -> set[PydanticObjectId]:
    libraries = await Library.find_all().to_list()
    items = await LibraryItem.find(
        LibraryItem.kind == LibraryItemKind.WORKFLOW
    ).to_list()
    return bookmarked_workflow_ids(libraries, items)


async def _fetch_referenced() -> set[str]:
    return referenced_workflow_ids(
        await Automation.find(Automation.action_type == "workflow").to_list(),
        await ProjectPin.find(ProjectPin.pin_type == "workflow").to_list(),
        await VerifiedItemMetadata.find(
            VerifiedItemMetadata.item_kind == "workflow"
        ).to_list(),
    )


async def _personal_library(user_id: str, cache: dict[str, Library]) -> Library:
    if user_id in cache:
        return cache[user_id]
    lib = await Library.find_one(
        Library.scope == LibraryScope.PERSONAL,
        Library.owner_user_id == user_id,
    )
    if not lib:
        now = datetime.datetime.now(datetime.timezone.utc)
        lib = Library(
            scope=LibraryScope.PERSONAL,
            title="My Library",
            owner_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        await lib.insert()
    cache[user_id] = lib
    return lib


async def adopt(dry_run: bool = False, only_user: str | None = None) -> dict[str, int]:
    settings = Settings()
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_host)
    db = client[settings.mongo_db]
    await init_beanie(
        database=db,
        document_models=[
            Automation,
            Library,
            LibraryItem,
            ProjectPin,
            VerifiedItemMetadata,
            Workflow,
        ],
    )

    bookmarked = await _fetch_bookmarked()
    referenced = await _fetch_referenced()

    scanned = 0
    adopted = 0
    skipped_referenced = 0
    by_owner: dict[str, int] = defaultdict(int)
    lib_cache: dict[str, Library] = {}

    # Phase 1 — scan only, writing nothing.
    #
    # Writing inside the cursor loop held it open across every insert, so a
    # ten-minute cursor expiry, a crash or a Ctrl-C left behind LibraryItem rows
    # that no library referenced: invisible, and re-running inserted a second
    # set rather than reusing them, so each attempt added more. Collecting the
    # orphans first closes the cursor before anything is written.
    orphans_by_owner: dict[str, list[Workflow]] = defaultdict(list)

    query = {"user_id": only_user} if only_user else {}
    async for wf in Workflow.find(query):
        scanned += 1
        if wf.id in bookmarked:
            continue
        if not is_orphan(wf, bookmarked, referenced):
            skipped_referenced += 1
            continue

        owner = wf.created_by_user_id or wf.user_id
        by_owner[owner] += 1
        adopted += 1
        print(f"  orphan: {wf.name!r}  id={wf.id}  owner={owner}")
        orphans_by_owner[owner].append(wf)

    # Phase 2 — write, one owner at a time.
    if not dry_run:
        now = datetime.datetime.now(datetime.timezone.utc)
        for owner, workflows in orphans_by_owner.items():
            lib = await _personal_library(owner, lib_cache)
            item_ids: list[PydanticObjectId] = []
            for wf in workflows:
                li = LibraryItem(
                    item_id=wf.id,
                    kind=LibraryItemKind.WORKFLOW,
                    added_by_user_id=owner,
                    verified=bool(wf.verified),
                    created_at=wf.created_at,
                )
                await li.insert()
                item_ids.append(li.id)

            # $push rather than save(). save() writes the whole items array from
            # the snapshot read when the library was first fetched, so anything
            # the owner bookmarked while the script ran would be overwritten
            # away — creating a fresh orphan of exactly the kind this repairs.
            await Library.get_motor_collection().update_one(
                {"_id": lib.id},
                {
                    "$push": {"items": {"$each": item_ids}},
                    "$set": {"updated_at": now},
                },
            )

    return {
        "scanned": scanned,
        "adopted": adopted,
        "skipped_referenced": skipped_referenced,
        "owners": len(by_owner),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change, write nothing"
    )
    parser.add_argument("--user", help="limit to one owner's workflows")
    args = parser.parse_args()

    stats = asyncio.run(adopt(dry_run=args.dry_run, only_user=args.user))
    verb = "would re-attach" if args.dry_run else "re-attached"
    print(
        f"\nScanned {stats['scanned']} workflows; {verb} {stats['adopted']} "
        f"orphan(s) across {stats['owners']} owner(s); "
        f"left {stats['skipped_referenced']} reachable from an automation, "
        f"project pin, or the verified catalog."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
