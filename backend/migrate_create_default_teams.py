"""
Pre-migration step for Flask -> Beanie migration.

Four phases, all idempotent:
  0. Drop all non-_id indexes from every collection. The Flask MongoEngine
     indexes restored from mongodump include unique constraints (e.g.
     `item_kind_1_item_identifier_1`) that fire when the Beanie migration
     unsets those legacy fields on multiple docs. Beanie will recreate its
     own declared indexes at app startup.
  1. Create a default team + owner membership for every user missing
     `current_team`, mirroring the new-app signup flow in
     `app/services/demo_service.py`.
  2. Delete content from team-scoped collections that has no `user_id`
     (pre-user-era records that can't be assigned to any team).
  3. Backfill `owner_user_id` on libraries that lack it:
     - scope=verified libraries -> "system" sentinel
     - scope=team libraries -> inherit from the referenced team's owner

Run BEFORE `migrate_flask_to_beanie.py`.

Usage:
    python migrate_create_default_teams.py --mongo-host mongodb://localhost:27018 --db-name vandalizer --dry-run
    python migrate_create_default_teams.py --mongo-host mongodb://localhost:27018 --db-name vandalizer
"""

import argparse
import datetime
import logging
import secrets
import sys

from bson import ObjectId
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("default_teams")


def run(mongo_host: str, db_name: str, dry_run: bool) -> int:
    client = MongoClient(mongo_host)
    db = client[db_name]
    now = datetime.datetime.now(datetime.timezone.utc)

    # --- Phase 0: drop legacy indexes ---
    log.info("Phase 0: drop non-_id indexes on all collections")
    dropped_total = 0
    for coll_name in db.list_collection_names():
        if coll_name.startswith("system.") or "_backup_" in coll_name:
            continue
        coll = db[coll_name]
        for idx_name in list(coll.index_information().keys()):
            if idx_name == "_id_":
                continue
            if dry_run:
                log.info("  DRY-RUN: would drop %s.%s", coll_name, idx_name)
            else:
                coll.drop_index(idx_name)
                log.info("  dropped %s.%s", coll_name, idx_name)
            dropped_total += 1
    log.info("Phase 0 done: %d indexes dropped.", dropped_total)
    log.info("")

    orphans = list(db.user.find(
        {"$or": [{"current_team": None}, {"current_team": {"$exists": False}}]},
        {"user_id": 1, "email": 1, "name": 1},
    ))

    log.info("Found %d users missing current_team", len(orphans))
    created = 0
    skipped = 0

    for u in orphans:
        uid = u.get("user_id")
        if not uid:
            log.warning("  skip: user %s has no user_id", u["_id"])
            skipped += 1
            continue

        # Idempotency: if a team owned by this user already exists, reuse it
        existing = db.team.find_one({"owner_user_id": uid})
        if existing:
            team_oid = existing["_id"]
            log.info("  reuse team %s for user %s", team_oid, uid)
        else:
            team_oid = ObjectId()
            team_doc = {
                "_id": team_oid,
                "uuid": secrets.token_urlsafe(12),
                "name": "My Team",
                "owner_user_id": uid,
                "organization_id": None,
                "created_at": now,
            }
            if dry_run:
                log.info("  DRY-RUN: create team %s (owner=%s)", team_oid, uid)
            else:
                db.team.insert_one(team_doc)
                log.info("  create team %s (owner=%s)", team_oid, uid)

        # Ensure owner membership
        mem = db.team_membership.find_one({"team": team_oid, "user_id": uid})
        if not mem:
            if dry_run:
                log.info("    DRY-RUN: create owner membership")
            else:
                db.team_membership.insert_one({
                    "team": team_oid,
                    "user_id": uid,
                    "role": "owner",
                    "created_at": now,
                })

        # Set current_team
        if dry_run:
            log.info("    DRY-RUN: set user.current_team = %s", team_oid)
        else:
            db.user.update_one(
                {"_id": u["_id"]},
                {"$set": {"current_team": team_oid}},
            )

        created += 1

    log.info("Phase 1 done: %d orphan users processed (skipped %d).", created, skipped)

    # --- Phase 2: delete ownerless content ---
    log.info("")
    log.info("Phase 2: remove team-scoped content with no user_id")
    orphan_collections = [
        "smart_document",
        "search_set",
        "workflow",
        "chat_conversation",
    ]
    total_deleted = 0
    for coll_name in orphan_collections:
        filt = {"user_id": {"$exists": False}}
        count = db[coll_name].count_documents(filt)
        if count == 0:
            continue
        if dry_run:
            log.info("  DRY-RUN: would delete %d %s with no user_id", count, coll_name)
        else:
            res = db[coll_name].delete_many(filt)
            log.info("  deleted %d %s with no user_id", res.deleted_count, coll_name)
            total_deleted += res.deleted_count

    log.info("Phase 2 done: %d ownerless docs removed.", total_deleted)

    # --- Phase 3: backfill library.owner_user_id ---
    log.info("")
    log.info("Phase 3: backfill library.owner_user_id")
    libs = list(db.library.find({
        "$or": [{"owner_user_id": None}, {"owner_user_id": {"$exists": False}}],
    }))
    patched = 0
    unpatched = 0
    for lib in libs:
        scope = lib.get("scope")
        owner = None
        if scope == "verified":
            owner = "system"
        elif lib.get("team"):
            team = db.team.find_one({"_id": lib["team"]})
            owner = team.get("owner_user_id") if team else None

        if not owner:
            log.warning("  could not resolve owner for library %s (scope=%s)",
                        lib["_id"], scope)
            unpatched += 1
            continue

        if dry_run:
            log.info("  DRY-RUN: library %s (scope=%s) -> owner=%s",
                     lib["_id"], scope, owner)
        else:
            db.library.update_one(
                {"_id": lib["_id"]},
                {"$set": {"owner_user_id": owner}},
            )
        patched += 1

    log.info("Phase 3 done: %d libraries patched (%d unresolved).",
             patched, unpatched)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-host", default="mongodb://localhost:27017/")
    parser.add_argument("--db-name", default="vandalizer")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(args.mongo_host, args.db_name, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
