#!/usr/bin/env python3
"""
Migrate uploaded document files from the old Flask app to the new system.

Reads SmartDocument records from the (already-migrated) database, locates
the corresponding file in a source folder, and copies it into the new
UPLOAD_DIR with the correct relative path so the FastAPI storage layer
can find it.

The old Flask app stored files in two layouts:
  1. Bare filename:        uploads/UUID.ext
  2. User-ID prefix:       uploads/{user_id}/UUID.ext

The new system expects files at:  UPLOAD_DIR/{doc.path}
where doc.path is the relative path stored in MongoDB (either "UUID.ext"
or "user_id/UUID.ext").

This script handles both layouts by searching the source folder for each
file by name, regardless of subfolder structure.

Usage:
    python migrate_files.py SOURCE_DIR                    # dry-run (default)
    python migrate_files.py SOURCE_DIR --apply            # copy files
    python migrate_files.py SOURCE_DIR --apply --dest DIR # custom dest
    python migrate_files.py SOURCE_DIR --verify           # check dest only

Examples:
    # Preview what will happen
    python migrate_files.py /path/to/old/uploads

    # Actually copy files into the default upload dir
    python migrate_files.py /path/to/old/uploads --apply

    # Verify files are already in place
    python migrate_files.py /path/to/old/uploads --verify
"""

import argparse
import hashlib
import logging
import shutil
import sys
from pathlib import Path

from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("migrate_files")


def build_source_index(source_dir: Path) -> dict[str, Path]:
    """Build a filename → full-path index of every file in source_dir.

    Walks the entire tree so we can find files regardless of whether they
    are in the root or in a user-ID subfolder.  If duplicates exist the
    one in a subfolder (user_id/UUID.ext) wins over a bare root copy.
    """
    index: dict[str, Path] = {}
    for p in source_dir.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        # Prefer files in subdirectories (user_id/UUID.ext) over root copies
        if name not in index or p.parent != source_dir:
            index[name] = p
    return index


def file_checksum(path: Path, algorithm: str = "sha256") -> str:
    """Return hex digest of *path* contents."""
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def migrate_files(
    db,
    source_dir: Path,
    dest_dir: Path,
    *,
    dry_run: bool = True,
    verify_only: bool = False,
    checksum: bool = False,
):
    coll = db["smart_document"]
    total = coll.count_documents({})
    log.info("SmartDocuments in database: %d", total)

    docs = list(coll.find({}, {"_id": 1, "path": 1, "downloadpath": 1, "title": 1}))

    # Build index of files in source directory
    log.info("Indexing source directory: %s", source_dir)
    source_index = build_source_index(source_dir)
    log.info("Found %d files in source", len(source_index))

    stats = {
        "found": 0,
        "already_in_dest": 0,
        "copied": 0,
        "missing": 0,
        "checksum_ok": 0,
        "checksum_mismatch": 0,
    }
    missing_files = []

    for doc in docs:
        doc_id = doc["_id"]
        rel_path = doc.get("downloadpath") or doc.get("path", "")
        if not rel_path:
            log.warning("  %s: no path or downloadpath — skipping", doc_id)
            stats["missing"] += 1
            continue

        filename = Path(rel_path).name
        dest_path = dest_dir / rel_path

        # --- verify-only mode: just check destination ---
        if verify_only:
            if dest_path.exists():
                stats["found"] += 1
                if checksum and filename in source_index:
                    src_hash = file_checksum(source_index[filename])
                    dst_hash = file_checksum(dest_path)
                    if src_hash == dst_hash:
                        stats["checksum_ok"] += 1
                    else:
                        stats["checksum_mismatch"] += 1
                        log.warning("  CHECKSUM MISMATCH %s", rel_path)
            else:
                stats["missing"] += 1
                missing_files.append(rel_path)
            continue

        # --- copy mode ---
        # Already at destination?
        if dest_path.exists():
            stats["already_in_dest"] += 1
            continue

        # Find in source
        source_path = source_index.get(filename)
        if not source_path:
            stats["missing"] += 1
            missing_files.append(rel_path)
            title = doc.get("title", "")
            log.warning("  MISSING %s (%s)", rel_path, title)
            continue

        stats["found"] += 1

        if dry_run:
            log.info("  DRY-RUN: %s -> %s", source_path, dest_path)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_path), str(dest_path))
            stats["copied"] += 1

    # --- report ---
    log.info("")
    log.info("=" * 60)

    if verify_only:
        log.info("VERIFY RESULTS")
        log.info("  Files present in dest:  %d / %d", stats["found"], total)
        log.info("  Missing from dest:      %d", stats["missing"])
        if checksum:
            log.info("  Checksum OK:            %d", stats["checksum_ok"])
            log.info("  Checksum mismatch:      %d", stats["checksum_mismatch"])
    else:
        log.info("MIGRATION RESULTS")
        log.info("  Already in dest:        %d", stats["already_in_dest"])
        log.info("  Found in source:        %d", stats["found"])
        if dry_run:
            log.info("  Would copy:             %d", stats["found"])
        else:
            log.info("  Copied:                 %d", stats["copied"])
        log.info("  Missing (not in source):%d", stats["missing"])

    if missing_files:
        log.info("")
        log.info("Missing files (first 20):")
        for mf in missing_files[:20]:
            log.info("  %s", mf)
        if len(missing_files) > 20:
            log.info("  ... and %d more", len(missing_files) - 20)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate uploaded document files to the new system",
    )
    parser.add_argument("source_dir",
                        help="Directory containing old Flask upload files")
    parser.add_argument("--apply", action="store_true",
                        help="Actually copy files (default is dry-run)")
    parser.add_argument("--verify", action="store_true",
                        help="Only check that files exist in destination")
    parser.add_argument("--checksum", action="store_true",
                        help="With --verify, also compare file checksums")
    parser.add_argument("--dest",
                        help="Destination upload dir "
                             "(default: resolved from app config)")
    parser.add_argument("--mongo-host",
                        default="mongodb://localhost:27017/",
                        help="MongoDB connection string")
    parser.add_argument("--db-name", default="vandalizer",
                        help="Database name")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.is_dir():
        log.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    # Resolve destination directory
    if args.dest:
        dest_dir = Path(args.dest).resolve()
    else:
        # Use the same path resolution as app/config.py
        backend_dir = Path(__file__).resolve().parent
        upload = Path("../app/static/uploads")
        dest_dir = (backend_dir / upload).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    log.info("Source:      %s", source_dir)
    log.info("Destination: %s", dest_dir)
    log.info("Mode:        %s",
             "VERIFY" if args.verify else ("APPLY" if args.apply else "DRY-RUN"))
    log.info("")

    client = MongoClient(args.mongo_host)
    db = client[args.db_name]

    stats = migrate_files(
        db,
        source_dir,
        dest_dir,
        dry_run=not args.apply,
        verify_only=args.verify,
        checksum=args.checksum,
    )

    if stats["missing"] > 0 and not args.verify:
        log.warning("%d file(s) could not be found in the source directory.",
                    stats["missing"])
        sys.exit(1)
    elif stats["missing"] > 0 and args.verify:
        log.warning("%d file(s) missing from destination.", stats["missing"])
        sys.exit(1)


if __name__ == "__main__":
    main()
