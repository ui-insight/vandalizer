#!/usr/bin/env python3
"""
Flask-to-Beanie full database migration.

Transforms MongoEngine documents in-place to comply with the Beanie schema,
without disrupting users or losing data.  Uses pymongo directly (no ORM).

Phases:
  0  Preflight   — count docs, build lookup maps
  1  Backups     — copy each collection to {name}_backup_{timestamp}
  2  Renames     — rename 3 collections whose names changed
  3  _cls removal— strip MongoEngine _cls from every collection
  4  Migrations  — per-collection schema changes (space→team_id, field
                   defaults, reference conversions, field removals)
  5  Verify      — post-migration integrity checks

Usage:
    python migrate_flask_to_beanie.py                              # full run
    python migrate_flask_to_beanie.py --dry-run                    # preview
    python migrate_flask_to_beanie.py --verify                     # checks only
    python migrate_flask_to_beanie.py --rollback                   # restore backups
    python migrate_flask_to_beanie.py --default-team-id <uuid>     # fallback team
    python migrate_flask_to_beanie.py --mongo-host <uri> --db-name <name>
"""

import argparse
import datetime
import logging
import sys

from bson import DBRef, ObjectId
from pymongo import MongoClient, UpdateOne

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("migrate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# Flask collection name → Beanie collection name
COLLECTION_RENAMES = {
    "workflow_trigger_events": "workflow_trigger_event",
    "graph_subscriptions": "graph_subscription",
    "m365_audit_log": "m365_audit_entry",
}

# Flask GenericReferenceField _cls → Beanie kind
CLS_TO_KIND = {
    "Workflow": "workflow",
    "SearchSet": "search_set",
}

# All Beanie target collection names (used for backup / verification)
ALL_COLLECTIONS = [
    "user", "team", "team_membership", "team_invite",
    "smart_document", "smart_folder",
    "search_set", "search_set_item",
    "workflow", "workflow_step", "workflow_step_task", "workflow_attachment",
    "workflow_result", "workflow_artifacts", "workflow_trigger_event",
    "chat_message", "chat_conversation",
    "file_attachment", "url_attachment",
    "library", "library_item", "library_folder",
    "knowledge_bases", "knowledge_base_sources",
    "system_config",
    "activity_event",
    "graph_subscription",
    "m365_audit_entry",
    "intake_configs", "work_items",
    "verification_request", "verified_item_metadata", "verified_collection",
    "extraction_quality_record",
    "validation_runs", "quality_alerts",
    "automation",
    "approval_request",
    "chat_feedback",
    "demo_application", "post_experience_response",
    "notification",
    "extraction_test_cases",
    "certification_progress",
    "audit_log", "admin_audit_log",
    "organization",
    "user_model_config",
    "kb_test_queries", "kb_suggestions",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_oid(value):
    """Extract an ObjectId from a value that may be ObjectId, DBRef, or dict."""
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, DBRef):
        return value.id
    if isinstance(value, dict):
        if "$id" in value:
            return value["$id"]
        ref = value.get("_ref")
        if isinstance(ref, DBRef):
            return ref.id
        if ref and "$id" in ref:
            return ref["$id"]
    return None


def backup_collection(db, name, batch_size=5000):
    """Copy *name* to a timestamped backup. Returns (backup_name, count)."""
    backup_name = f"{name}_backup_{TIMESTAMP}"
    coll = db[name]
    total = coll.count_documents({})
    if total == 0:
        log.info("  %s: empty — skipping backup", name)
        return backup_name, 0

    batch = []
    for doc in coll.find():
        batch.append(doc)
        if len(batch) >= batch_size:
            db[backup_name].insert_many(batch)
            batch = []
    if batch:
        db[backup_name].insert_many(batch)

    log.info("  %s -> %s (%d docs)", name, backup_name, total)
    return backup_name, total


def _set_defaults(db, coll_name, defaults, dry_run, existing):
    """Set default values for fields that don't exist yet (idempotent)."""
    if coll_name not in existing:
        return
    coll = db[coll_name]
    for field, default_val in defaults.items():
        count = coll.count_documents({field: {"$exists": False}})
        if count == 0:
            continue
        if dry_run:
            log.info("    DRY-RUN: %s.%s = %r on %d docs",
                     coll_name, field, default_val, count)
        else:
            result = coll.update_many(
                {field: {"$exists": False}},
                {"$set": {field: default_val}},
            )
            log.info("    %s.%s: set default on %d docs",
                     coll_name, field, result.modified_count)


def _unset_fields(db, coll_name, fields, dry_run, existing):
    """Remove *fields* from every document in *coll_name*."""
    if coll_name not in existing:
        return
    coll = db[coll_name]
    or_query = [{f: {"$exists": True}} for f in fields]
    count = coll.count_documents({"$or": or_query})
    if count == 0:
        return
    if dry_run:
        log.info("    DRY-RUN: %s: would unset %s on %d docs",
                 coll_name, fields, count)
    else:
        result = coll.update_many(
            {"$or": or_query},
            {"$unset": {f: "" for f in fields}},
        )
        log.info("    %s: unset %s on %d docs",
                 coll_name, fields, result.modified_count)


# ===================================================================
# Phase 0 — Preflight
# ===================================================================

def phase0_preflight(db, default_team_id):
    log.info("=" * 60)
    log.info("PHASE 0 — Preflight")
    log.info("=" * 60)

    existing = set(db.list_collection_names())
    pre_counts = {}

    for name in sorted(existing):
        if name.startswith("_") or name.startswith("system."):
            continue
        count = db[name].count_documents({})
        pre_counts[name] = count
        log.info("  %s: %d", name, count)

    # --- team _id → uuid map ---
    team_oid_uuid = {}
    if "team" in existing:
        for doc in db["team"].find({}, {"_id": 1, "uuid": 1}):
            team_oid_uuid[doc["_id"]] = doc.get("uuid", str(doc["_id"]))

    # --- user_id → team uuid map ---
    user_team_map = {}  # user_id (str) → team uuid (str)
    if "user" in existing:
        for doc in db["user"].find({}, {"user_id": 1, "current_team": 1}):
            uid = doc.get("user_id")
            if not uid:
                continue
            ct = doc.get("current_team")
            team_oid = extract_oid(ct) if ct is not None else None
            if team_oid and team_oid in team_oid_uuid:
                user_team_map[uid] = team_oid_uuid[team_oid]
            elif default_team_id:
                user_team_map[uid] = default_team_id

    log.info("  User->team map: %d users mapped", len(user_team_map))
    total_users = pre_counts.get("user", 0)
    unmapped = total_users - len(user_team_map)
    if unmapped > 0:
        if default_team_id:
            log.info("  %d users have no team -> default %s", unmapped, default_team_id)
        else:
            log.warning("  %d users have no team mapping (use --default-team-id)",
                        unmapped)

    # --- KB _id → uuid map ---
    kb_id_uuid = {}
    if "knowledge_bases" in existing:
        for doc in db["knowledge_bases"].find({}, {"_id": 1, "uuid": 1}):
            kb_id_uuid[doc["_id"]] = doc.get("uuid", "")
    log.info("  KB _id->uuid map: %d entries", len(kb_id_uuid))

    # Persist pre-migration counts
    db["_migration_metadata"].update_one(
        {"_id": "preflight"},
        {"$set": {
            "pre_counts": pre_counts,
            "timestamp": TIMESTAMP,
            "user_team_map_size": len(user_team_map),
            "kb_map_size": len(kb_id_uuid),
        }},
        upsert=True,
    )

    return pre_counts, user_team_map, kb_id_uuid


# ===================================================================
# Phase 1 — Backups
# ===================================================================

def phase1_backups(db, dry_run):
    log.info("=" * 60)
    log.info("PHASE 1 — Backups")
    log.info("=" * 60)

    existing = set(db.list_collection_names())
    to_backup = set()

    for name in ALL_COLLECTIONS:
        if name in existing:
            to_backup.add(name)
    # Include pre-rename names so we back up the originals
    for old in COLLECTION_RENAMES:
        if old in existing:
            to_backup.add(old)

    manifest = {}
    for name in sorted(to_backup):
        if dry_run:
            count = db[name].count_documents({})
            log.info("  DRY-RUN: would backup %s (%d docs)", name, count)
            manifest[name] = f"{name}_backup_{TIMESTAMP}"
        else:
            bname, _ = backup_collection(db, name)
            manifest[name] = bname

    if not dry_run:
        db["_migration_metadata"].update_one(
            {"_id": "backup_manifest"},
            {"$set": {"manifest": manifest, "timestamp": TIMESTAMP}},
            upsert=True,
        )
    return manifest


# ===================================================================
# Phase 2 — Collection Renames
# ===================================================================

def phase2_renames(db, dry_run):
    log.info("=" * 60)
    log.info("PHASE 2 — Collection Renames")
    log.info("=" * 60)

    existing = set(db.list_collection_names())

    for old, new in COLLECTION_RENAMES.items():
        if old in existing and new not in existing:
            if dry_run:
                count = db[old].count_documents({})
                log.info("  DRY-RUN: %s -> %s (%d docs)", old, new, count)
            else:
                db[old].rename(new)
                log.info("  Renamed %s -> %s", old, new)
        elif new in existing:
            log.info("  %s already exists — skipping rename from %s", new, old)
        else:
            log.info("  %s does not exist — skipping", old)


# ===================================================================
# Phase 3 — Global _cls Removal
# ===================================================================

def phase3_cls_removal(db, dry_run):
    log.info("=" * 60)
    log.info("PHASE 3 — Global _cls Removal")
    log.info("=" * 60)

    for name in sorted(db.list_collection_names()):
        if name.startswith("_") or name.startswith("system.") or "_backup_" in name:
            continue
        coll = db[name]
        count = coll.count_documents({"_cls": {"$exists": True}})
        if count == 0:
            continue
        if dry_run:
            log.info("  DRY-RUN: %s: would remove _cls from %d docs", name, count)
        else:
            result = coll.update_many(
                {"_cls": {"$exists": True}},
                {"$unset": {"_cls": ""}},
            )
            log.info("  %s: removed _cls from %d docs", name, result.modified_count)


# ===================================================================
# Phase 4 — Per-Collection Schema Migrations
# ===================================================================

def phase4_migrations(db, user_team_map, kb_id_uuid, default_team_id, dry_run):
    log.info("=" * 60)
    log.info("PHASE 4 — Per-Collection Schema Migrations")
    log.info("=" * 60)

    existing = set(db.list_collection_names())

    # ------------------------------------------------------------------
    # 4a  Space → team_id mapping
    # ------------------------------------------------------------------
    log.info("-- 4a. Space -> team_id mapping")

    for coll_name in ["smart_document", "search_set", "workflow",
                       "chat_conversation", "knowledge_bases"]:
        if coll_name not in existing:
            log.info("  %s: not found — skipping", coll_name)
            continue

        coll = db[coll_name]
        need = coll.count_documents({"team_id": {"$exists": False}})
        log.info("  %s: %d docs need team_id", coll_name, need)

        if need > 0:
            migrated = 0
            for user_id, team_id in user_team_map.items():
                filt = {"user_id": user_id, "team_id": {"$exists": False}}
                if dry_run:
                    c = coll.count_documents(filt)
                    if c:
                        log.info("    DRY-RUN: user=%s -> team_id=%s (%d docs)",
                                 user_id, team_id, c)
                    migrated += c
                else:
                    r = coll.update_many(
                        filt,
                        {"$set": {"team_id": team_id}, "$unset": {"space": ""}},
                    )
                    migrated += r.modified_count

            remaining = coll.count_documents({"team_id": {"$exists": False}})
            if remaining > 0 and default_team_id:
                if dry_run:
                    log.info("    DRY-RUN: %d orphans -> default team %s",
                             remaining, default_team_id)
                else:
                    coll.update_many(
                        {"team_id": {"$exists": False}},
                        {"$set": {"team_id": default_team_id},
                         "$unset": {"space": ""}},
                    )
                migrated += remaining
            elif remaining > 0:
                log.warning("    %s: %d docs still lack team_id "
                            "(use --default-team-id)", coll_name, remaining)

            if not dry_run:
                log.info("  %s: set team_id on %d docs", coll_name, migrated)

        # Clean up any lingering space fields
        space_left = coll.count_documents({"space": {"$exists": True}})
        if space_left:
            if dry_run:
                log.info("    DRY-RUN: unset remaining space on %d docs", space_left)
            else:
                coll.update_many(
                    {"space": {"$exists": True}},
                    {"$unset": {"space": ""}},
                )
                log.info("    Unset remaining space on %d docs", space_left)

    # SmartFolder / ActivityEvent already have team_id — just drop space
    for coll_name in ["smart_folder", "activity_event"]:
        _unset_fields(db, coll_name, ["space"], dry_run, existing)

    # ------------------------------------------------------------------
    # 4b  New field defaults
    # ------------------------------------------------------------------
    log.info("-- 4b. New field defaults")

    _set_defaults(db, "user", {
        "is_demo_user": False,
        "demo_expires_at": None,
        "demo_status": None,
        "organization_id": None,
    }, dry_run, existing)

    _set_defaults(db, "team", {
        "organization_id": None,
    }, dry_run, existing)

    _set_defaults(db, "smart_document", {
        "classification": None,
        "classification_confidence": None,
        "classified_at": None,
        "classified_by": None,
        "retention_hold": False,
        "retention_hold_reason": None,
        "scheduled_deletion_at": None,
        "soft_deleted": False,
        "soft_deleted_at": None,
        "token_count": 0,
        "num_pages": 0,
        "user_id": "unknown",
        "raw_text": "",
    }, dry_run, existing)

    # Copy path → downloadpath for docs that lack it
    if "smart_document" in existing:
        coll = db["smart_document"]
        need_dp = list(coll.find(
            {"downloadpath": {"$exists": False}, "path": {"$exists": True}},
            {"_id": 1, "path": 1},
        ))
        if need_dp:
            if dry_run:
                log.info("    DRY-RUN: smart_document.downloadpath: "
                         "copy from path on %d docs", len(need_dp))
            else:
                ops = [
                    UpdateOne({"_id": d["_id"]},
                              {"$set": {"downloadpath": d["path"]}})
                    for d in need_dp
                ]
                coll.bulk_write(ops)
                log.info("    smart_document.downloadpath: copied from path "
                         "on %d docs", len(ops))

    _set_defaults(db, "search_set", {
        "item_order": [],
        "domain": None,
        "cross_field_rules": [],
        "set_type": "extraction",
    }, dry_run, existing)

    _set_defaults(db, "search_set_item", {
        "is_optional": False,
        "enum_values": [],
    }, dry_run, existing)
    _unset_fields(db, "search_set_item", ["space_id"], dry_run, existing)

    _set_defaults(db, "workflow", {
        "validation_plan": [],
        "validation_inputs": [],
    }, dry_run, existing)

    _set_defaults(db, "workflow_result", {
        "paused_at_step_index": None,
        "approval_request_id": None,
        "batch_id": None,
        "document_title": None,
    }, dry_run, existing)
    _unset_fields(db, "workflow_result", ["trigger_event"], dry_run, existing)

    _set_defaults(db, "chat_message", {
        "thinking": None,
        "thinking_duration": None,
    }, dry_run, existing)

    _set_defaults(db, "system_config", {
        "quality_config": {},
        "classification_config": {},
        "retention_config": {},
        "default_team_id": None,
    }, dry_run, existing)

    _set_defaults(db, "graph_subscription", {
        "client_state": None,
        "team_id": None,
    }, dry_run, existing)

    _set_defaults(db, "verified_item_metadata", {
        "organization_ids": [],
        "quality_score": None,
        "quality_tier": None,
        "quality_grade": None,
        "last_validated_at": None,
        "validation_run_count": 0,
    }, dry_run, existing)

    _set_defaults(db, "extraction_quality_record", {
        "user_id": None,
        "search_set_uuid": None,
        "created_at": datetime.datetime.now(datetime.UTC),
    }, dry_run, existing)

    # ------------------------------------------------------------------
    # 4c  Reference field conversions
    # ------------------------------------------------------------------
    log.info("-- 4c. Reference field conversions")

    _migrate_library_items(db, dry_run, existing)
    _migrate_kb_sources(db, kb_id_uuid, dry_run, existing)
    _migrate_verification_requests(db, dry_run, existing)
    _migrate_verified_collections(db, dry_run, existing)
    _migrate_verified_item_metadata(db, dry_run, existing)
    _ensure_library_owner(db, dry_run, existing)

    # ------------------------------------------------------------------
    # 4d  Field removals & DBRef cleanup
    # ------------------------------------------------------------------
    log.info("-- 4d. Field removals & DBRef cleanup")

    _unset_fields(db, "knowledge_bases", ["sources"], dry_run, existing)
    _cleanup_dbrefs(db, dry_run, existing)


# -- 4c sub-routines ---------------------------------------------------

def _migrate_library_items(db, dry_run, existing):
    """GenericReferenceField obj → flat item_id / kind.

    Incorporates logic from the original migrate.py.
    """
    if "library_item" not in existing:
        return

    coll = db["library_item"]
    log.info("  LibraryItem migration")

    # 0. Remove items whose kind is unsupported in Beanie (e.g. SearchSetItem
    #    prompts/formatters — the new UI only supports workflow/search_set/
    #    knowledge_base).
    UNSUPPORTED_KINDS = {"prompt", "formatter"}
    unsupported_cls = {"SearchSetItem"}

    unsup_query = {"$or": [
        {"kind": {"$in": list(UNSUPPORTED_KINDS)}},
        {"obj._cls": {"$in": list(unsupported_cls)}},
    ]}
    unsup_count = coll.count_documents(unsup_query)
    if unsup_count:
        if dry_run:
            log.info("    DRY-RUN: would remove %d library items with "
                     "unsupported kinds %s (SearchSetItem references)",
                     unsup_count, UNSUPPORTED_KINDS)
        else:
            coll.delete_many(unsup_query)
            log.info("    Removed %d library items with unsupported kinds %s "
                     "(SearchSetItem references — not supported in new UI)",
                     unsup_count, UNSUPPORTED_KINDS)

    # 1. Convert obj → item_id / kind
    docs = list(coll.find(
        {"obj": {"$exists": True}, "item_id": {"$exists": False}},
    ))
    stats = {"migrated": 0, "errors": 0}

    for doc in docs:
        doc_id = doc["_id"]
        obj = doc.get("obj")
        if not obj:
            continue

        item_id = extract_oid(obj)
        if not item_id:
            log.error("    LibraryItem %s: cannot extract ObjectId from obj: %s",
                      doc_id, obj)
            stats["errors"] += 1
            continue

        cls_name = obj.get("_cls", "") if isinstance(obj, dict) else ""
        kind = CLS_TO_KIND.get(cls_name)
        if not kind:
            existing_kind = doc.get("kind", "")
            if existing_kind == "searchset":
                kind = "search_set"
            elif existing_kind in ("workflow", "search_set", "knowledge_base"):
                kind = existing_kind
            else:
                log.error("    LibraryItem %s: unknown _cls=%r, kind=%r",
                          doc_id, cls_name, existing_kind)
                stats["errors"] += 1
                continue

        if dry_run:
            log.info("    DRY-RUN: %s -> item_id=%s, kind=%s", doc_id, item_id, kind)
        else:
            coll.update_one(
                {"_id": doc_id},
                {"$set": {"item_id": item_id, "kind": kind}},
            )
        stats["migrated"] += 1

    log.info("    obj->item_id/kind: %d migrated, %d errors",
             stats["migrated"], stats["errors"])

    # 2. Normalize kind "searchset" → "search_set"
    count = coll.count_documents({"kind": "searchset"})
    if count:
        if dry_run:
            log.info("    DRY-RUN: normalize 'searchset'->'search_set' on %d docs", count)
        else:
            coll.update_many({"kind": "searchset"}, {"$set": {"kind": "search_set"}})
            log.info("    Normalized 'searchset'->'search_set' on %d docs", count)

    # 3. Add new fields
    _set_defaults(db, "library_item", {
        "pinned": False,
        "favorited": False,
        "last_used_at": None,
    }, dry_run, existing)

    # 4. Copy added_at → created_at
    docs_ts = list(coll.find(
        {"added_at": {"$exists": True}, "created_at": {"$exists": False}},
        {"_id": 1, "added_at": 1},
    ))
    if docs_ts:
        if dry_run:
            log.info("    DRY-RUN: copy added_at->created_at on %d docs", len(docs_ts))
        else:
            ops = [
                UpdateOne({"_id": d["_id"]}, {"$set": {"created_at": d["added_at"]}})
                for d in docs_ts
            ]
            coll.bulk_write(ops)
            log.info("    Copied added_at->created_at on %d docs", len(ops))

    # 5. Remove old fields
    _unset_fields(db, "library_item", ["obj", "added_at"], dry_run, existing)


def _migrate_kb_sources(db, kb_id_uuid, dry_run, existing):
    """knowledge_base (ObjectId ref) → knowledge_base_uuid (string)."""
    if "knowledge_base_sources" not in existing:
        return

    coll = db["knowledge_base_sources"]
    log.info("  KnowledgeBaseSource migration")

    docs = list(coll.find(
        {"knowledge_base": {"$exists": True},
         "knowledge_base_uuid": {"$exists": False}},
        {"_id": 1, "knowledge_base": 1},
    ))

    stats = {"migrated": 0, "errors": 0}
    for doc in docs:
        doc_id = doc["_id"]
        kb_ref = doc.get("knowledge_base")
        kb_oid = extract_oid(kb_ref) if not isinstance(kb_ref, ObjectId) else kb_ref

        if not kb_oid:
            log.error("    KBSource %s: cannot extract KB ObjectId from %s",
                      doc_id, kb_ref)
            stats["errors"] += 1
            continue

        kb_uuid = kb_id_uuid.get(kb_oid, "")
        if not kb_uuid:
            log.warning("    KBSource %s: KB %s not in map — using empty uuid",
                        doc_id, kb_oid)

        if dry_run:
            log.info("    DRY-RUN: KBSource %s: knowledge_base_uuid=%s",
                     doc_id, kb_uuid)
        else:
            coll.update_one(
                {"_id": doc_id},
                {"$set": {"knowledge_base_uuid": kb_uuid}},
            )
        stats["migrated"] += 1

    log.info("    knowledge_base->uuid: %d migrated, %d errors",
             stats["migrated"], stats["errors"])

    # Add crawl fields
    _set_defaults(db, "knowledge_base_sources", {
        "crawl_enabled": False,
        "max_crawl_pages": 5,
        "parent_source_uuid": None,
        "crawled_urls": None,
    }, dry_run, existing)

    # Remove old reference fields
    _unset_fields(db, "knowledge_base_sources",
                  ["knowledge_base", "document"], dry_run, existing)


def _migrate_verification_requests(db, dry_run, existing):
    """item_identifier (string) → item_id (ObjectId), add new fields."""
    if "verification_request" not in existing:
        return

    coll = db["verification_request"]
    log.info("  VerificationRequest migration")

    # Remove verification requests for unsupported item kinds
    unsup_kinds = {"prompt", "formatter"}
    unsup_count = coll.count_documents({"item_kind": {"$in": list(unsup_kinds)}})
    if unsup_count:
        if dry_run:
            log.info("    DRY-RUN: would remove %d verification requests with "
                     "unsupported item_kind %s", unsup_count, unsup_kinds)
        else:
            coll.delete_many({"item_kind": {"$in": list(unsup_kinds)}})
            log.info("    Removed %d verification requests with unsupported "
                     "item_kind %s", unsup_count, unsup_kinds)

    docs = list(coll.find(
        {"item_identifier": {"$exists": True},
         "item_id": {"$exists": False}},
        {"_id": 1, "item_identifier": 1, "item_kind": 1},
    ))

    stats = {"migrated": 0, "errors": 0}
    for doc in docs:
        doc_id = doc["_id"]
        identifier = doc.get("item_identifier", "")
        item_kind = doc.get("item_kind", "")

        # Try parsing as ObjectId first
        item_oid = None
        try:
            item_oid = ObjectId(identifier)
        except Exception:
            # May be a UUID — look up the item by uuid
            if item_kind in ("searchset", "search_set"):
                found = db["search_set"].find_one(
                    {"uuid": identifier}, {"_id": 1})
                if found:
                    item_oid = found["_id"]

        if not item_oid:
            log.error("    VerifReq %s: cannot resolve item_identifier=%r",
                      doc_id, identifier)
            stats["errors"] += 1
            continue

        if dry_run:
            log.info("    DRY-RUN: VerifReq %s: item_id=%s", doc_id, item_oid)
        else:
            coll.update_one(
                {"_id": doc_id},
                {"$set": {"item_id": item_oid}},
            )
        stats["migrated"] += 1

    log.info("    item_identifier->item_id: %d migrated, %d errors",
             stats["migrated"], stats["errors"])

    # Normalize item_kind "searchset" → "search_set"
    count = coll.count_documents({"item_kind": "searchset"})
    if count:
        if dry_run:
            log.info("    DRY-RUN: normalize item_kind on %d docs", count)
        else:
            coll.update_many(
                {"item_kind": "searchset"},
                {"$set": {"item_kind": "search_set"}},
            )
            log.info("    Normalized item_kind on %d docs", count)

    # Add new fields
    _set_defaults(db, "verification_request", {
        "validation_snapshot": None,
        "validation_score": None,
        "validation_tier": None,
        "return_guidance": None,
        "reviewer_user_id": None,
        "reviewer_notes": None,
    }, dry_run, existing)

    # Remove old fields
    _unset_fields(db, "verification_request",
                  ["item_identifier", "library_item", "item_title"],
                  dry_run, existing)


def _migrate_verified_collections(db, dry_run, existing):
    """items (ObjectId list) → item_ids (string list), add featured."""
    if "verified_collection" not in existing:
        return

    coll = db["verified_collection"]
    log.info("  VerifiedCollection migration")

    docs = list(coll.find(
        {"items": {"$exists": True}, "item_ids": {"$exists": False}},
        {"_id": 1, "items": 1},
    ))

    if docs:
        if dry_run:
            log.info("    DRY-RUN: convert items->item_ids on %d docs", len(docs))
        else:
            ops = []
            for doc in docs:
                items = doc.get("items", [])
                item_ids = [str(extract_oid(i) or i) for i in items]
                ops.append(UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"item_ids": item_ids}},
                ))
            if ops:
                coll.bulk_write(ops)
            log.info("    Converted items->item_ids on %d docs", len(ops))

    # Add featured field
    _set_defaults(db, "verified_collection", {"featured": False}, dry_run, existing)

    # Remove old field
    _unset_fields(db, "verified_collection", ["items"], dry_run, existing)


def _migrate_verified_item_metadata(db, dry_run, existing):
    """item_identifier → item_id (string copy)."""
    if "verified_item_metadata" not in existing:
        return

    coll = db["verified_item_metadata"]
    log.info("  VerifiedItemMetadata migration")

    docs = list(coll.find(
        {"item_identifier": {"$exists": True},
         "item_id": {"$exists": False}},
        {"_id": 1, "item_identifier": 1},
    ))

    if docs:
        if dry_run:
            log.info("    DRY-RUN: copy item_identifier->item_id on %d docs",
                     len(docs))
        else:
            ops = [
                UpdateOne(
                    {"_id": d["_id"]},
                    {"$set": {"item_id": d["item_identifier"]}},
                )
                for d in docs
            ]
            coll.bulk_write(ops)
            log.info("    Copied item_identifier->item_id on %d docs", len(ops))

    # Normalize item_kind
    count = coll.count_documents({"item_kind": "searchset"})
    if count:
        if dry_run:
            log.info("    DRY-RUN: normalize item_kind on %d docs", count)
        else:
            coll.update_many(
                {"item_kind": "searchset"},
                {"$set": {"item_kind": "search_set"}},
            )
            log.info("    Normalized item_kind on %d docs", count)

    # Remove old field
    _unset_fields(db, "verified_item_metadata",
                  ["item_identifier"], dry_run, existing)


def _ensure_library_owner(db, dry_run, existing):
    """Warn about Library / LibraryFolder docs missing owner_user_id."""
    for coll_name in ["library", "library_folder"]:
        if coll_name not in existing:
            continue
        count = db[coll_name].count_documents({"owner_user_id": {"$exists": False}})
        if count:
            log.warning("  %s: %d docs missing owner_user_id — "
                        "manual fix may be needed", coll_name, count)


def _cleanup_dbrefs(db, dry_run, existing):
    """Convert DBRef-formatted references to plain ObjectIds."""
    log.info("  DBRef cleanup")

    # ReferenceFields known to exist in Flask
    dbref_fields = {
        "user": ["current_team"],
        "team_membership": ["team"],
        "team_invite": ["team"],
        "workflow_result": ["workflow"],
        "workflow_trigger_event": ["workflow", "workflow_result", "work_item"],
        "library": ["team"],
        "library_folder": ["team"],
    }

    for coll_name, fields in dbref_fields.items():
        if coll_name not in existing:
            continue
        coll = db[coll_name]
        for field in fields:
            # DBRef stores as dict with $ref key
            query = {f"{field}.$ref": {"$exists": True}}
            docs = list(coll.find(query, {"_id": 1, field: 1}))
            if not docs:
                continue
            if dry_run:
                log.info("    DRY-RUN: %s.%s: %d DBRefs to convert",
                         coll_name, field, len(docs))
            else:
                ops = []
                for doc in docs:
                    oid = extract_oid(doc[field])
                    if oid:
                        ops.append(UpdateOne(
                            {"_id": doc["_id"]},
                            {"$set": {field: oid}},
                        ))
                if ops:
                    coll.bulk_write(ops)
                    log.info("    %s.%s: converted %d DBRefs",
                             coll_name, field, len(ops))


# ===================================================================
# Phase 5 — Verification
# ===================================================================

def phase5_verify(db):
    log.info("=" * 60)
    log.info("PHASE 5 — Verification")
    log.info("=" * 60)

    existing = set(db.list_collection_names())
    issues = []

    # 1. Zero _cls fields
    for name in sorted(existing):
        if name.startswith("_") or name.startswith("system.") or "_backup_" in name:
            continue
        count = db[name].count_documents({"_cls": {"$exists": True}})
        if count:
            issues.append(f"{name}: {count} docs still have _cls")

    # 2. Zero space fields on migrated collections
    for name in ["smart_document", "smart_folder", "search_set", "workflow",
                  "knowledge_bases", "activity_event"]:
        if name in existing:
            count = db[name].count_documents({"space": {"$exists": True}})
            if count:
                issues.append(f"{name}: {count} docs still have space")

    # 3. All space-scoped docs have team_id
    for name in ["smart_document", "search_set", "workflow",
                  "chat_conversation", "knowledge_bases"]:
        if name in existing:
            count = db[name].count_documents({"team_id": {"$exists": False}})
            if count:
                issues.append(f"{name}: {count} docs missing team_id")

    # 4. LibraryItem
    if "library_item" in existing:
        li = db["library_item"]
        for field, label in [("obj", "still have obj"),
                             ("item_id", "missing item_id"),
                             ("kind", "missing kind")]:
            q = {field: {"$exists": field == "obj"}}
            if field != "obj":
                q = {field: {"$exists": False}}
            c = li.count_documents(q)
            if c:
                issues.append(f"library_item: {c} docs {label}")
        c = li.count_documents({"kind": "searchset"})
        if c:
            issues.append(f"library_item: {c} docs still have kind='searchset'")

    # 5. KnowledgeBaseSource
    if "knowledge_base_sources" in existing:
        c = db["knowledge_base_sources"].count_documents(
            {"knowledge_base_uuid": {"$exists": False}})
        if c:
            issues.append(f"knowledge_base_sources: {c} docs missing knowledge_base_uuid")

    # 6. VerificationRequest
    if "verification_request" in existing:
        c = db["verification_request"].count_documents(
            {"item_id": {"$exists": False}})
        if c:
            issues.append(f"verification_request: {c} docs missing item_id")

    # 7. VerifiedCollection
    if "verified_collection" in existing:
        c = db["verified_collection"].count_documents(
            {"item_ids": {"$exists": False}})
        if c:
            issues.append(f"verified_collection: {c} docs missing item_ids")

    # 8. Old collection names should be gone
    for old, new in COLLECTION_RENAMES.items():
        if old in existing:
            issues.append(f"old collection '{old}' still exists "
                          f"(should be renamed to '{new}')")

    # 9. Document counts match pre-migration baseline
    #    library_item is expected to shrink (unsupported kinds removed).
    EXPECTED_SHRINK = {"library_item", "verification_request"}
    meta = db["_migration_metadata"].find_one({"_id": "preflight"})
    if meta:
        pre = meta.get("pre_counts", {})
        for name, pre_count in pre.items():
            check = COLLECTION_RENAMES.get(name, name)
            if check in existing:
                post_count = db[check].count_documents({})
                if post_count != pre_count:
                    if check in EXPECTED_SHRINK and post_count < pre_count:
                        log.info("  OK  %s: count %d -> %d (expected — "
                                 "unsupported items removed)", check,
                                 pre_count, post_count)
                    else:
                        issues.append(
                            f"{check}: count changed {pre_count} -> {post_count}")

    # -- report --
    if issues:
        log.warning("Verification found %d issue(s):", len(issues))
        for i in issues:
            log.warning("  FAIL  %s", i)
    else:
        log.info("Verification passed — all checks OK")

    return issues


# ===================================================================
# Rollback
# ===================================================================

def rollback(db, dry_run):
    log.info("=" * 60)
    log.info("ROLLBACK — Restoring from backups")
    log.info("=" * 60)

    meta = db["_migration_metadata"].find_one({"_id": "backup_manifest"})
    if not meta:
        log.error("No backup manifest found — cannot rollback.")
        return False

    manifest = meta.get("manifest", {})
    ts = meta.get("timestamp", "unknown")
    log.info("Restoring backups created at %s", ts)

    existing = set(db.list_collection_names())

    for original, backup_name in sorted(manifest.items()):
        if backup_name not in existing:
            log.warning("  Backup %s not found — skipping %s", backup_name, original)
            continue

        backup_count = db[backup_name].count_documents({})

        if dry_run:
            log.info("  DRY-RUN: %s -> %s (%d docs)", backup_name, original,
                     backup_count)
            continue

        # Drop whatever the collection is currently named
        current = COLLECTION_RENAMES.get(original, original)
        for name in {current, original}:
            if name in existing:
                db.drop_collection(name)
                log.info("  Dropped %s", name)

        db[backup_name].rename(original)
        log.info("  Restored %s -> %s (%d docs)", backup_name, original,
                 backup_count)

    log.info("Rollback complete")
    return True


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Migrate Flask/MongoEngine database to Beanie schema",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview all changes without writing")
    parser.add_argument("--verify", action="store_true",
                        help="Run post-migration verification checks only")
    parser.add_argument("--rollback", action="store_true",
                        help="Restore all collections from backups")
    parser.add_argument("--default-team-id", default=None,
                        help="Fallback team UUID for content without a team")
    parser.add_argument("--mongo-host",
                        default="mongodb://localhost:27017/",
                        help="MongoDB connection string")
    parser.add_argument("--db-name", default="osp",
                        help="Database name")
    args = parser.parse_args()

    client = MongoClient(args.mongo_host)
    db = client[args.db_name]

    log.info("Database: %s%s", args.mongo_host, args.db_name)

    # --- verify-only mode ---
    if args.verify:
        issues = phase5_verify(db)
        sys.exit(1 if issues else 0)

    # --- rollback mode ---
    if args.rollback:
        ok = rollback(db, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)

    # --- full migration ---
    log.info("Mode: %s", "DRY-RUN" if args.dry_run else "LIVE")
    log.info("")

    pre_counts, user_team_map, kb_id_uuid = phase0_preflight(
        db, args.default_team_id)

    phase1_backups(db, dry_run=args.dry_run)
    phase2_renames(db, dry_run=args.dry_run)
    phase3_cls_removal(db, dry_run=args.dry_run)
    phase4_migrations(db, user_team_map, kb_id_uuid,
                      args.default_team_id, dry_run=args.dry_run)

    log.info("")
    issues = phase5_verify(db)

    if issues:
        log.warning("Migration completed with %d verification issue(s)",
                    len(issues))
        sys.exit(1)
    else:
        log.info("Migration completed successfully")


if __name__ == "__main__":
    main()
