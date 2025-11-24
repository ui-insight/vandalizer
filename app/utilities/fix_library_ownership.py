#!/usr/bin/env python3
"""
Script to diagnose and fix library ownership issues when user IDs have changed.

Usage:
    # Diagnose issues for a specific user
    python -m app.utilities.fix_library_ownership --email jbrunsfeld@uidaho.edu --diagnose
    
    # Fix ownership for a specific user
    python -m app.utilities.fix_library_ownership --email jbrunsfeld@uidaho.edu --fix
"""

import argparse
from mongoengine import Q
from app.models import User, SearchSet, Workflow, SearchSetItem, LibraryItem, Library
from app.utilities.library_helpers import _get_or_create_personal_library, _ensure_library_item


def diagnose_user(email: str):
    """Diagnose library ownership issues for a user"""
    print(f"\n{'='*70}")
    print(f"DIAGNOSING USER: {email}")
    print(f"{'='*70}")
    
    # Find user
    user = User.objects(email=email).first()
    if not user:
        print(f"❌ User with email {email} not found!")
        return
    
    print(f"\n✅ Found user:")
    print(f"   Email: {user.email}")
    print(f"   User ID: {user.user_id}")
    print(f"   Name: {user.name}")
    
    # Check for objects owned by this user (by email or user_id)
    user_q = (
        Q(created_by_user_id=user.user_id) | Q(user_id=user.user_id) |
        Q(created_by_user_id=user.email) | Q(user_id=user.email)
    )
    
    search_sets = list(SearchSet.objects(user_q))
    workflows = list(Workflow.objects(user_q))
    prompts = list(SearchSetItem.objects(user_q & Q(searchtype="prompt")))
    formatters = list(SearchSetItem.objects(user_q & Q(searchtype="formatter")))
    
    print(f"\n📦 Objects owned by this user:")
    print(f"   SearchSets: {len(search_sets)}")
    print(f"   Workflows: {len(workflows)}")
    print(f"   Prompts: {len(prompts)}")
    print(f"   Formatters: {len(formatters)}")
    
    # Check personal library
    lib = Library.objects(scope='personal', owner_user_id=user.user_id).first()
    if not lib:
        print(f"\n⚠️  No personal library found for this user!")
        print(f"   Will be created when running --fix")
    else:
        print(f"\n✅ Personal library found:")
        print(f"   Library ID: {lib.id}")
        print(f"   Items in library: {len(lib.items)}")
        
        # Check which objects are in the library
        lib_searchsets = [li.obj for li in lib.items if li.kind == "searchset" and li.obj]
        lib_workflows = [li.obj for li in lib.items if li.kind == "workflow" and li.obj]
        lib_prompts = [li.obj for li in lib.items if li.kind == "prompt" and li.obj]
        lib_formatters = [li.obj for li in lib.items if li.kind == "formatter" and li.obj]
        
        print(f"\n📊 Items in personal library:")
        print(f"   SearchSets: {len(lib_searchsets)}")
        print(f"   Workflows: {len(lib_workflows)}")
        print(f"   Prompts: {len(lib_prompts)}")
        print(f"   Formatters: {len(lib_formatters)}")
        
        # Find missing items
        missing_ss = [ss for ss in search_sets if ss not in lib_searchsets]
        missing_wf = [wf for wf in workflows if wf not in lib_workflows]
        missing_prompts = [p for p in prompts if p not in lib_prompts]
        missing_formatters = [f for f in formatters if f not in lib_formatters]
        
        if missing_ss or missing_wf or missing_prompts or missing_formatters:
            print(f"\n⚠️  Missing from library:")
            if missing_ss:
                print(f"   SearchSets: {len(missing_ss)}")
                for ss in missing_ss[:5]:
                    print(f"      - {ss.uuid}: {ss.title} (user_id={ss.user_id}, created_by={ss.created_by_user_id})")
            if missing_wf:
                print(f"   Workflows: {len(missing_wf)}")
                for wf in missing_wf[:5]:
                    print(f"      - {wf.id}: {wf.name} (user_id={wf.user_id}, created_by={wf.created_by_user_id})")
            if missing_prompts:
                print(f"   Prompts: {len(missing_prompts)}")
            if missing_formatters:
                print(f"   Formatters: {len(missing_formatters)}")
        else:
            print(f"\n✅ All owned objects are in the library!")
    
    # Check for orphaned LibraryItems
    print(f"\n🔍 Checking for orphaned LibraryItems...")
    all_objects = search_sets + workflows + prompts + formatters
    orphaned_items = []
    
    for obj in all_objects:
        # Determine kind
        if isinstance(obj, SearchSet):
            kind = "searchset"
        elif isinstance(obj, Workflow):
            kind = "workflow"
        elif isinstance(obj, SearchSetItem) and obj.searchtype == "prompt":
            kind = "prompt"
        elif isinstance(obj, SearchSetItem) and obj.searchtype == "formatter":
            kind = "formatter"
        else:
            continue
        
        # Check if LibraryItem exists
        li = LibraryItem.objects(obj=obj, kind=kind).first()
        if li:
            # Check if it's in any library
            in_any_lib = False
            for library in Library.objects():
                if li in library.items:
                    in_any_lib = True
                    if library.scope == 'personal' and library.owner_user_id != user.user_id:
                        orphaned_items.append((obj, li, library))
                    break
            
            if not in_any_lib:
                orphaned_items.append((obj, li, None))
    
    if orphaned_items:
        print(f"\n⚠️  Found {len(orphaned_items)} orphaned LibraryItems:")
        for obj, li, wrong_lib in orphaned_items[:10]:
            obj_name = getattr(obj, 'title', None) or getattr(obj, 'name', None) or str(obj.id)
            if wrong_lib:
                print(f"   - {obj_name} (in library of user {wrong_lib.owner_user_id})")
            else:
                print(f"   - {obj_name} (not in any library)")


def fix_user(email: str):
    """Fix library ownership for a user"""
    print(f"\n{'='*70}")
    print(f"FIXING USER: {email}")
    print(f"{'='*70}")
    
    # Find user
    user = User.objects(email=email).first()
    if not user:
        print(f"❌ User with email {email} not found!")
        return
    
    print(f"\n✅ Found user: {user.email} (ID: {user.user_id})")
    
    # Get or create personal library
    lib = _get_or_create_personal_library(user.user_id)
    print(f"✅ Personal library: {lib.id}")
    
    # Find all objects owned by this user
    user_q = (
        Q(created_by_user_id=user.user_id) | Q(user_id=user.user_id) |
        Q(created_by_user_id=user.email) | Q(user_id=user.email)
    )
    
    items_added = 0
    items_existing = 0
    
    # SearchSets
    for ss in SearchSet.objects(user_q):
        existing = LibraryItem.objects(obj=ss, kind="searchset").first()
        if existing and existing in lib.items:
            items_existing += 1
        else:
            _ensure_library_item(lib, ss, "searchset")
            items_added += 1
    
    # Workflows
    for wf in Workflow.objects(user_q):
        existing = LibraryItem.objects(obj=wf, kind="workflow").first()
        if existing and existing in lib.items:
            items_existing += 1
        else:
            _ensure_library_item(lib, wf, "workflow")
            items_added += 1
    
    # Prompts
    for p in SearchSetItem.objects(user_q & Q(searchtype="prompt")):
        existing = LibraryItem.objects(obj=p, kind="prompt").first()
        if existing and existing in lib.items:
            items_existing += 1
        else:
            _ensure_library_item(lib, p, "prompt")
            items_added += 1
    
    # Formatters
    for f in SearchSetItem.objects(user_q & Q(searchtype="formatter")):
        existing = LibraryItem.objects(obj=f, kind="formatter").first()
        if existing and existing in lib.items:
            items_existing += 1
        else:
            _ensure_library_item(lib, f, "formatter")
            items_added += 1
    
    print(f"\n✅ Fixed library:")
    print(f"   Items added: {items_added}")
    print(f"   Items already existed: {items_existing}")
    print(f"   Total items in library: {len(lib.items)}")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose and fix library ownership issues"
    )
    parser.add_argument(
        '--email',
        type=str,
        required=True,
        help='Email of user to diagnose/fix'
    )
    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Diagnose issues (read-only)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Fix issues (write to database)'
    )
    
    args = parser.parse_args()
    
    if not args.diagnose and not args.fix:
        print("❌ Please specify either --diagnose or --fix")
        return
    
    if args.diagnose:
        diagnose_user(args.email)
    
    if args.fix:
        fix_user(args.email)


if __name__ == "__main__":
    main()
