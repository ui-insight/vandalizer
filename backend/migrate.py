"""
One-time migration: Convert LibraryItem GenericReferenceField to flat item_id/kind fields.

Flask's MongoEngine GenericReferenceField stores:
    "obj": {"_cls": "Workflow", "_ref": {"$ref": "workflow", "$id": ObjectId("...")}}

FastAPI's Beanie model expects:
    "item_id": ObjectId("...")
    "kind": "workflow" | "search_set"

This script reads each library_item document and:
1. Extracts the ObjectId from obj._ref.$id → item_id
2. Maps obj._cls to the FastAPI kind value → kind

Run with:
    python migrate.py              # Apply changes
    python migrate.py --dry-run    # Preview without writing
    python migrate.py --rollback   # Reverse migration (remove item_id/kind fields)
    python migrate.py --verify     # Check migration integrity
"""

import argparse
import datetime
import sys

from pymongo import MongoClient

# Flask _cls values → FastAPI kind values
CLS_TO_KIND = {
    "Workflow": "workflow",
    "SearchSet": "search_set",
}


def backup_collection(db, collection_name: str) -> str:
    """Copy collection to a timestamped backup. Returns backup collection name."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{collection_name}_backup_{timestamp}"
    docs = list(db[collection_name].find())
    if docs:
        db[backup_name].insert_many(docs)
    print(f"Backed up {len(docs)} documents to {backup_name}")
    return backup_name


def migrate_library_items(db, dry_run: bool = False) -> dict:
    collection = db["library_item"]

    # Find documents that have the old GenericReferenceField but no item_id yet
    query = {"obj": {"$exists": True}, "item_id": {"$exists": False}}
    docs = list(collection.find(query))

    stats = {"total": len(docs), "migrated": 0, "skipped": 0, "errors": []}
    print(f"Found {len(docs)} library_item documents to migrate")

    for doc in docs:
        doc_id = doc["_id"]
        obj = doc.get("obj")

        if not obj:
            stats["skipped"] += 1
            print(f"  SKIP {doc_id}: missing obj field")
            continue

        # Extract ObjectId from GenericReferenceField structure
        ref = obj.get("_ref")
        if ref and "$id" in ref:
            item_id = ref["$id"]
        elif "$id" in obj:
            # Alternate serialization format
            item_id = obj["$id"]
        else:
            stats["errors"].append(str(doc_id))
            print(f"  ERROR {doc_id}: cannot extract ObjectId from obj: {obj}")
            continue

        # Map _cls to FastAPI kind value
        cls_name = obj.get("_cls", "")
        kind = CLS_TO_KIND.get(cls_name)
        if not kind:
            # Fall back to existing kind field if present
            existing_kind = doc.get("kind", "")
            # Normalize Flask's "searchset" to FastAPI's "search_set"
            if existing_kind == "searchset":
                kind = "search_set"
            elif existing_kind in ("workflow", "search_set"):
                kind = existing_kind
            else:
                stats["errors"].append(str(doc_id))
                print(f"  ERROR {doc_id}: unknown _cls={cls_name!r}, kind={existing_kind!r}")
                continue

        if dry_run:
            print(f"  DRY-RUN {doc_id}: item_id={item_id}, kind={kind}")
        else:
            collection.update_one(
                {"_id": doc_id},
                {"$set": {"item_id": item_id, "kind": kind}},
            )
            print(f"  MIGRATED {doc_id}: item_id={item_id}, kind={kind}")

        stats["migrated"] += 1

    return stats


def rollback_library_items(db, dry_run: bool = False) -> dict:
    """Reverse the migration: remove item_id/kind fields from documents
    that still have the original obj field."""
    collection = db["library_item"]

    query = {"item_id": {"$exists": True}, "obj": {"$exists": True}}
    docs = list(collection.find(query))

    stats = {"total": len(docs), "rolled_back": 0}
    print(f"Found {len(docs)} library_item documents to roll back")

    for doc in docs:
        doc_id = doc["_id"]
        if dry_run:
            print(f"  DRY-RUN rollback {doc_id}")
        else:
            collection.update_one(
                {"_id": doc_id},
                {"$unset": {"item_id": "", "kind": ""}},
            )
            print(f"  ROLLED BACK {doc_id}")
        stats["rolled_back"] += 1

    return stats


def verify_migration(db) -> dict:
    """Check migration integrity: every library_item should have item_id and kind."""
    collection = db["library_item"]

    total = collection.count_documents({})
    with_item_id = collection.count_documents({"item_id": {"$exists": True}})
    with_kind = collection.count_documents({"kind": {"$exists": True}})
    with_obj_no_item_id = collection.count_documents(
        {"obj": {"$exists": True}, "item_id": {"$exists": False}}
    )

    stats = {
        "total": total,
        "with_item_id": with_item_id,
        "with_kind": with_kind,
        "unmigrated": with_obj_no_item_id,
    }

    print(f"Total library_item documents: {total}")
    print(f"  With item_id: {with_item_id}")
    print(f"  With kind: {with_kind}")
    print(f"  Unmigrated (have obj but no item_id): {with_obj_no_item_id}")

    if with_obj_no_item_id > 0:
        print("\nWARNING: Some documents still need migration!")
    else:
        print("\nMigration verified: all documents have been migrated.")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate LibraryItem GenericReferenceField to flat fields")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--rollback", action="store_true", help="Reverse the migration")
    parser.add_argument("--verify", action="store_true", help="Check migration integrity")
    parser.add_argument("--no-backup", action="store_true", help="Skip automatic backup before migration")
    parser.add_argument("--mongo-host", default="mongodb://localhost:27017/", help="MongoDB connection string")
    parser.add_argument("--db-name", default="osp", help="Database name")
    args = parser.parse_args()

    client = MongoClient(args.mongo_host)
    db = client[args.db_name]

    print(f"Database: {args.db_name}")
    print()

    if args.verify:
        verify_migration(db)
        return

    if args.rollback:
        print(f"Dry run: {args.dry_run}")
        print()
        if not args.dry_run and not args.no_backup:
            backup_collection(db, "library_item")
            print()
        stats = rollback_library_items(db, dry_run=args.dry_run)
        print()
        print(f"Results: {stats['rolled_back']} rolled back out of {stats['total']}")
        return

    print(f"Dry run: {args.dry_run}")
    print()

    if not args.dry_run and not args.no_backup:
        backup_collection(db, "library_item")
        print()

    stats = migrate_library_items(db, dry_run=args.dry_run)

    print()
    print(f"Results: {stats['migrated']} migrated, {stats['skipped']} skipped, {len(stats['errors'])} errors")
    if stats["errors"]:
        print(f"Error document IDs: {stats['errors']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
