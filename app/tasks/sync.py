#!/usr/bin/env python3

import os
import requests
import json
from celery import shared_task
from flask import current_app
from mongoengine import DoesNotExist
from app.models import (
    Workflow, SearchSet, SearchSetItem, VerificationStatus
)
from app.utilities.library_helpers import add_object_to_library, get_or_create_verified_library

@shared_task(name="tasks.sync.pull_verified_items")
def pull_verified_items():
    is_main = os.getenv("IS_MAIN_SERVER", "false").lower() == "true"
    if is_main:
        return "Skipped (Main Server)"

    url = os.getenv("MAIN_SERVER_URL")
    key = os.getenv("SYNC_API_KEY")
    instance_name = os.getenv("INSTANCE_NAME", "Unknown Instance")
    if not url: return "No Main URL configured"

    try:
        resp = requests.get(
            f"{url}/library/api/sync/verified",
            headers={"X-Sync-Key": key, "X-Instance-Name": instance_name},
            timeout=30
        )
        if resp.status_code != 200:
            return f"Sync failed: {resp.text}"
        
        items = resp.json().get("items", [])
    except Exception as e:
        return f"Sync connection error: {e}"

    count = 0
    verified_lib = get_or_create_verified_library()

    for item in items:
        kind = item['kind']
        uuid = item['uuid']
        data = item['data']
        
        # Determine Model
        ModelClass = None
        if kind == 'workflow': ModelClass = Workflow
        elif kind == 'searchset': ModelClass = SearchSet
        elif kind in ['prompt', 'formatter']: ModelClass = SearchSetItem
        
        if not ModelClass: continue

        try:
            # Check for local existence
            if kind == 'searchset':
                local_obj = ModelClass.objects(uuid=uuid).first()
            else:
                local_obj = ModelClass.objects(id=uuid).first()

            if not local_obj:
                # Create new from Prod data
                local_obj = ModelClass.from_json(json.dumps(data))
                # Ensure ID consistency
                if kind != 'searchset': local_obj.id = uuid
            else:
                # Update existing
                local_obj.update(**data)
                local_obj.reload()

            # Mark as Verified Locally
            if hasattr(local_obj, 'verified'):
                local_obj.verified = True
                local_obj.save()

            # Ensure it is in the Verified Library
            add_object_to_library(local_obj, verified_lib, added_by_user_id="sync_bot")
            count += 1
        except Exception as e:
            print(f"Error syncing {kind} {uuid}: {e}")

    return f"Synced {count} verified items."
