#!/usr/bin/env python3
"""Merge duplicate user records that share the same identity/email."""

from __future__ import annotations

import argparse

from app import app
from app.utilities.user_identity import (
    find_duplicate_identity_keys,
    find_identity_matches,
    normalize_identity,
    resolve_user_identity,
)


def _run_for_identity(identity_key: str, dry_run: bool) -> int:
    matches = find_identity_matches(
        user_id_hint=identity_key,
        email_hint=identity_key,
    )
    if len(matches) <= 1:
        return 0

    canonical_user = resolve_user_identity(
        user_id_hint=identity_key,
        email_hint=identity_key,
        create_if_missing=False,
        auto_merge_duplicates=False,
    )
    if not canonical_user:
        return 0

    duplicate_users = [u for u in matches if str(u.id) != str(canonical_user.id)]
    duplicate_user_ids = [u.user_id for u in duplicate_users]

    if dry_run:
        print(
            f"[DRY-RUN] identity='{identity_key}' canonical='{canonical_user.user_id}' "
            f"duplicates={duplicate_user_ids}"
        )
        return len(duplicate_users)

    resolve_user_identity(
        user_id_hint=identity_key,
        email_hint=identity_key,
        create_if_missing=False,
        auto_merge_duplicates=True,
    )
    print(
        f"[MERGED] identity='{identity_key}' canonical='{canonical_user.user_id}' "
        f"duplicates={duplicate_user_ids}"
    )
    return len(duplicate_users)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge duplicate user records by email/user identity."
    )
    parser.add_argument(
        "--email",
        help="Merge duplicates for a single email/identity key.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview duplicate groups without modifying data.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of identity groups to process (0 = no limit).",
    )
    args = parser.parse_args()

    with app.app_context():
        if args.email:
            identity = normalize_identity(args.email)
            if not identity:
                print("No valid identity provided.")
                return 1
            identity_keys = [identity]
        else:
            identity_keys = find_duplicate_identity_keys()

        if args.limit and args.limit > 0:
            identity_keys = identity_keys[: args.limit]

        if not identity_keys:
            print("No duplicate user identities found.")
            return 0

        merged_user_count = 0
        for identity_key in identity_keys:
            merged_user_count += _run_for_identity(identity_key, dry_run=args.dry_run)

        action = "Would merge" if args.dry_run else "Merged"
        print(f"{action} {merged_user_count} duplicate user record(s).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
