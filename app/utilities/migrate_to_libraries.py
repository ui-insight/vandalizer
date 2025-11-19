#!/usr/bin/env python3
"""
Migration script to backfill personal libraries from existing search_sets and workflows.

This script:
1. Creates personal libraries for all users
2. Backfills library_items pointing to existing search_sets and workflows
3. Handles orphaned search_sets (no owner) by assigning to fallback user
4. Provides detailed reporting and verification

Usage:
    # Dry run (no changes)
    python -m app.utilities.migrate_to_libraries --dry-run

    # Actually run migration
    python -m app.utilities.migrate_to_libraries

    # Run with custom fallback user
    python -m app.utilities.migrate_to_libraries --fallback-email admin@example.com
"""

import argparse
import sys
from datetime import datetime, timezone
from collections import defaultdict

from app.models import User, SearchSet, SearchSetItem, Workflow, LibraryItem, Library
from app.utilities.library_helpers import (
    _get_or_create_personal_library,
    _ensure_library_item,
    _owner_id_for
)


class MigrationReport:
    """Track migration statistics and issues"""

    def __init__(self):
        self.users_processed = 0
        self.users_skipped = 0
        self.libraries_created = 0
        self.library_items_created = 0
        self.library_items_existing = 0
        self.search_sets_migrated = 0
        self.workflows_migrated = 0
        self.prompts_migrated = 0
        self.formatters_migrated = 0
        self.orphaned_search_sets = []
        self.orphaned_workflows = []
        self.errors = []
        self.user_details = defaultdict(lambda: {
            'search_sets': 0,
            'workflows': 0,
            'library_items_created': 0,
            'library_items_existing': 0
        })

    def print_summary(self):
        """Print detailed migration summary"""
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)

        print(f"\n📊 Overall Statistics:")
        print(f"  Users processed: {self.users_processed}")
        print(f"  Users skipped: {self.users_skipped}")
        print(f"  Libraries created: {self.libraries_created}")
        print(f"  LibraryItems created: {self.library_items_created}")
        print(f"  LibraryItems already existed: {self.library_items_existing}")

        print(f"\n📦 Objects Migrated:")
        print(f"  SearchSets: {self.search_sets_migrated}")
        print(f"  Workflows: {self.workflows_migrated}")
        print(f"  Prompts: {self.prompts_migrated}")
        print(f"  Formatters: {self.formatters_migrated}")

        if self.orphaned_search_sets:
            print(f"\n⚠️  Orphaned SearchSets (no owner): {len(self.orphaned_search_sets)}")
            for ss in self.orphaned_search_sets[:10]:  # Show first 10
                print(f"    - {ss.uuid}: {ss.title}")
            if len(self.orphaned_search_sets) > 10:
                print(f"    ... and {len(self.orphaned_search_sets) - 10} more")

        if self.orphaned_workflows:
            print(f"\n⚠️  Orphaned Workflows (no owner): {len(self.orphaned_workflows)}")
            for wf in self.orphaned_workflows[:10]:
                print(f"    - {wf.id}: {wf.title}")
            if len(self.orphaned_workflows) > 10:
                print(f"    ... and {len(self.orphaned_workflows) - 10} more")

        if self.errors:
            print(f"\n❌ Errors: {len(self.errors)}")
            for error in self.errors:
                print(f"    - {error}")

        if not self.errors and not self.orphaned_search_sets and not self.orphaned_workflows:
            print(f"\n✅ Migration completed successfully with no issues!")


def find_orphaned_data():
    """Find search_sets and workflows with no owner"""
    orphaned_ss = []
    orphaned_wf = []

    print("\n🔍 Scanning for orphaned data...")

    for ss in SearchSet.objects():
        owner_id = _owner_id_for(ss)
        if not owner_id:
            orphaned_ss.append(ss)

    for wf in Workflow.objects():
        owner_id = _owner_id_for(wf)
        if not owner_id:
            orphaned_wf.append(wf)

    return orphaned_ss, orphaned_wf


def assign_orphaned_to_fallback(orphaned_objects, fallback_user, report, dry_run=False):
    """Assign orphaned objects to fallback user's library"""
    if not orphaned_objects:
        return

    obj_type = "SearchSet" if isinstance(orphaned_objects[0], SearchSet) else "Workflow"
    kind = "searchset" if obj_type == "SearchSet" else "workflow"

    print(f"\n📌 Assigning {len(orphaned_objects)} orphaned {obj_type}s to {fallback_user.email}")

    if dry_run:
        print(f"   [DRY RUN] Would assign to user: {fallback_user.user_id}")
        for obj in orphaned_objects[:5]:
            obj_id = obj.uuid if obj_type == "SearchSet" else obj.id
            print(f"   [DRY RUN] Would assign: {obj_id} - {obj.title}")
        if len(orphaned_objects) > 5:
            print(f"   [DRY RUN] ... and {len(orphaned_objects) - 5} more")
        return

    # Get or create fallback user's library
    fallback_lib = _get_or_create_personal_library(fallback_user.user_id)

    for obj in orphaned_objects:
        try:
            # Assign ownership
            obj.user_id = fallback_user.user_id
            obj.created_by_user_id = fallback_user.user_id
            obj.save()

            # Create library item
            _ensure_library_item(fallback_lib, obj, kind)

            if obj_type == "SearchSet":
                report.search_sets_migrated += 1
            else:
                report.workflows_migrated += 1

            report.user_details[fallback_user.email][f"{kind}s"] += 1

        except Exception as e:
            error_msg = f"Failed to assign {obj_type} {obj.uuid if obj_type == 'SearchSet' else obj.id}: {e}"
            report.errors.append(error_msg)
            print(f"   ❌ {error_msg}")


def backfill_user_library(user, report, dry_run=False):
    """Backfill a single user's personal library"""
    try:
        user_email = user.email or user.user_id

        if dry_run:
            print(f"\n[DRY RUN] Processing user: {user_email}")
        else:
            print(f"\n🔄 Processing user: {user_email}")

        # Get or create library
        if dry_run:
            lib = Library.objects(scope='personal', owner_user_id=user.user_id).first()
            if not lib:
                print(f"   [DRY RUN] Would create personal library for {user_email}")
                report.libraries_created += 1
        else:
            lib = _get_or_create_personal_library(user.user_id)
            if lib.items == [] or len(lib.items) == 0:
                report.libraries_created += 1

        # Count user's objects
        from mongoengine.queryset.visitor import Q
        user_q = Q(created_by_user_id=user.user_id) | Q(user_id=user.user_id)

        search_sets = SearchSet.objects(user_q)
        workflows = Workflow.objects(user_q)

        ss_count = search_sets.count()
        wf_count = workflows.count()

        if dry_run:
            print(f"   [DRY RUN] Found {ss_count} SearchSets, {wf_count} Workflows")

            # Sample a few
            if ss_count > 0:
                print(f"   [DRY RUN] Sample SearchSets:")
                for ss in search_sets[:3]:
                    existing = LibraryItem.objects(obj=ss, kind="searchset").first()
                    status = "already exists" if existing else "would create"
                    print(f"      - {ss.uuid}: {ss.title} ({status})")

            if wf_count > 0:
                print(f"   [DRY RUN] Sample Workflows:")
                for wf in workflows[:3]:
                    existing = LibraryItem.objects(obj=wf, kind="workflow").first()
                    status = "already exists" if existing else "would create"
                    print(f"      - {wf.id}: {wf.title} ({status})")

            report.search_sets_migrated += ss_count
            report.workflows_migrated += wf_count
        else:
            # Actually migrate
            items_created = 0
            items_existing = 0

            for ss in search_sets:
                existing = LibraryItem.objects(obj=ss, kind="searchset").first()
                if existing:
                    items_existing += 1
                    report.library_items_existing += 1
                else:
                    items_created += 1
                    report.library_items_created += 1

                _ensure_library_item(lib, ss, "searchset")
                report.search_sets_migrated += 1

            for wf in workflows:
                existing = LibraryItem.objects(obj=wf, kind="workflow").first()
                if existing:
                    items_existing += 1
                    report.library_items_existing += 1
                else:
                    items_created += 1
                    report.library_items_created += 1

                _ensure_library_item(lib, wf, "workflow")
                report.workflows_migrated += 1

            print(f"   ✅ Created {items_created} new items, {items_existing} already existed")

            report.user_details[user_email]['search_sets'] = ss_count
            report.user_details[user_email]['workflows'] = wf_count
            report.user_details[user_email]['library_items_created'] = items_created
            report.user_details[user_email]['library_items_existing'] = items_existing

        report.users_processed += 1

    except Exception as e:
        error_msg = f"Error processing user {user.email or user.user_id}: {e}"
        report.errors.append(error_msg)
        print(f"   ❌ {error_msg}")
        report.users_skipped += 1


def verify_migration():
    """Verify migration completed successfully"""
    print("\n" + "="*70)
    print("VERIFICATION CHECK")
    print("="*70)

    issues = []

    # Check each user has a personal library
    users_without_lib = []
    for user in User.objects():
        lib = Library.objects(scope='personal', owner_user_id=user.user_id).first()
        if not lib:
            users_without_lib.append(user.email or user.user_id)

    if users_without_lib:
        issues.append(f"❌ {len(users_without_lib)} users without personal library")
        for email in users_without_lib[:5]:
            print(f"   - {email}")
        if len(users_without_lib) > 5:
            print(f"   ... and {len(users_without_lib) - 5} more")
    else:
        print("✅ All users have personal libraries")

    # Check for search_sets not in any library
    orphaned_ss = []
    for ss in SearchSet.objects():
        li = LibraryItem.objects(obj=ss).first()
        if not li:
            orphaned_ss.append(f"{ss.uuid}: {ss.title}")

    if orphaned_ss:
        issues.append(f"❌ {len(orphaned_ss)} SearchSets not in any library")
        for ss_info in orphaned_ss[:5]:
            print(f"   - {ss_info}")
        if len(orphaned_ss) > 5:
            print(f"   ... and {len(orphaned_ss) - 5} more")
    else:
        print("✅ All SearchSets are in libraries")

    # Check for workflows not in any library
    orphaned_wf = []
    for wf in Workflow.objects():
        li = LibraryItem.objects(obj=wf).first()
        if not li:
            orphaned_wf.append(f"{wf.id}: {wf.title}")

    if orphaned_wf:
        issues.append(f"❌ {len(orphaned_wf)} Workflows not in any library")
        for wf_info in orphaned_wf[:5]:
            print(f"   - {wf_info}")
        if len(orphaned_wf) > 5:
            print(f"   ... and {len(orphaned_wf) - 5} more")
    else:
        print("✅ All Workflows are in libraries")

    # Summary
    print(f"\n📊 Database Statistics:")
    print(f"   Total Users: {User.objects.count()}")
    print(f"   Total Libraries: {Library.objects.count()}")
    print(f"   Total LibraryItems: {LibraryItem.objects.count()}")
    print(f"   Total SearchSets: {SearchSet.objects.count()}")
    print(f"   Total Workflows: {Workflow.objects.count()}")

    if not issues:
        print("\n✅ Verification passed! All data migrated successfully.")
    else:
        print(f"\n⚠️  Found {len(issues)} issues that need attention.")

    return len(issues) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Migrate search_sets and workflows to personal libraries"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would happen without making changes'
    )
    parser.add_argument(
        '--fallback-email',
        type=str,
        default='jbrunsfeld@uidaho.edu',
        help='Email of user to assign orphaned objects to (default: jbrunsfeld@uidaho.edu)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only run verification, skip migration'
    )

    args = parser.parse_args()

    # Print header
    print("="*70)
    print("LIBRARY MIGRATION SCRIPT")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")

    print(f"Fallback user for orphaned data: {args.fallback_email}")
    print("="*70)

    # Verify only mode
    if args.verify_only:
        verify_migration()
        return

    # Initialize report
    report = MigrationReport()

    # Find fallback user
    fallback_user = User.objects(email=args.fallback_email).first()
    if not fallback_user:
        print(f"❌ ERROR: Fallback user {args.fallback_email} not found!")
        print("   Available users:")
        for user in User.objects()[:10]:
            print(f"   - {user.email or user.user_id}")
        sys.exit(1)

    print(f"✅ Found fallback user: {fallback_user.email} (ID: {fallback_user.user_id})")

    # Find orphaned data
    orphaned_ss, orphaned_wf = find_orphaned_data()
    report.orphaned_search_sets = orphaned_ss
    report.orphaned_workflows = orphaned_wf

    print(f"   Found {len(orphaned_ss)} orphaned SearchSets")
    print(f"   Found {len(orphaned_wf)} orphaned Workflows")

    # Handle orphaned data first
    if orphaned_ss or orphaned_wf:
        if orphaned_ss:
            assign_orphaned_to_fallback(orphaned_ss, fallback_user, report, dry_run=args.dry_run)
        if orphaned_wf:
            assign_orphaned_to_fallback(orphaned_wf, fallback_user, report, dry_run=args.dry_run)

    # Process all users
    print(f"\n{'='*70}")
    print(f"PROCESSING {User.objects.count()} USERS")
    print(f"{'='*70}")

    for user in User.objects():
        backfill_user_library(user, report, dry_run=args.dry_run)

    # Print report
    report.print_summary()

    # Run verification if not dry run
    if not args.dry_run:
        print("\n" + "="*70)
        print("Running post-migration verification...")
        print("="*70)
        verify_migration()
    else:
        print("\n💡 Tip: Run without --dry-run to actually perform the migration")
        print("       Run with --verify-only to check current state")


if __name__ == "__main__":
    main()
