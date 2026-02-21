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
"""

import argparse
import sys

from pymongo import MongoClient

# Flask _cls values → FastAPI kind values
CLS_TO_KIND = {
    "Workflow": "workflow",
    "SearchSet": "search_set",
}


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


def main():
    parser = argparse.ArgumentParser(description="Migrate LibraryItem GenericReferenceField to flat fields")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--mongo-host", default="mongodb://localhost:27017/", help="MongoDB connection string")
    parser.add_argument("--db-name", default="osp", help="Database name")
    args = parser.parse_args()

    client = MongoClient(args.mongo_host)
    db = client[args.db_name]

    print(f"Database: {args.db_name}")
    print(f"Dry run: {args.dry_run}")
    print()

    stats = migrate_library_items(db, dry_run=args.dry_run)

    print()
    print(f"Results: {stats['migrated']} migrated, {stats['skipped']} skipped, {len(stats['errors'])} errors")
    if stats["errors"]:
        print(f"Error document IDs: {stats['errors']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
