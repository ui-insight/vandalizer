"""Handles file routing."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, url_for
from flask_login import login_required
from mongoengine.errors import DoesNotExist
from flask_mail import Message
from werkzeug.utils import secure_filename

from app import load_user, mail
from app.utilities.security import validate_json_request
from app.models import (  # adjust import path if needed
    Library,
    LibraryFolder,
    LibraryItem,
    LibraryScope,
    SearchSet,
    SearchSetItem,
    Team,
    TeamMembership,
    User,
    VerifiedCollection,
    VerifiedItemMetadata,
    VerificationRequest,
    VerificationStatus,
    Workflow,
    WorkflowAttachment,
    WorkflowStep,
    WorkflowStepTask,
    UserModelConfig,
    ActivityEvent,
    ActivityType,
)
from mongoengine import Q
from app.utilities.library_helpers import (
    add_object_to_library,
    get_or_create_personal_library,
    get_or_create_team_library,
    get_or_create_verified_library,
    sync_verification_flags_for_object,
)

library = Blueprint("library", __name__)

MAX_LIBRARY_WORKFLOWS = 40
MAX_LIBRARY_EXTRACTIONS = 60
MAX_LIBRARY_PROMPTS = 60
MAX_LIBRARY_FORMATTERS = 60


# -----------------------------
# Helpers to resolve scope
# -----------------------------
def _current_user_id() -> str:
    # Replace with your auth/session lookup
    # e.g. return session["user_id"]
    # For now, assume a dev user:
    return "dev-user-1"


def _current_user() -> User | None:
    return User.objects(user_id=_current_user_id()).first()


def _current_team_for_user(user: User | None) -> Team | None:
    if not user:
        return None
    return user.ensure_current_team()


# -----------------------------
# Kind / object resolvers
# -----------------------------
def _resolve_obj(kind: str, uuid_or_id: str):
    """
    kind: 'workflow' | 'extraction' | 'prompt' | 'formatter'
    uuid_or_id: for workflows = .id; search sets = .uuid; search set items (prompt/formatter) = .id
    Returns (obj, normalized_kind) or (None, None)
    """
    k = (kind or "").strip().lower()
    if k in ("workflow", "workflows"):
        obj = Workflow.objects(id=uuid_or_id).first()
        return (obj, "workflow")
    if k in ("extraction", "extract", "searchset", "search_set", "extractions"):
        obj = SearchSet.objects(uuid=uuid_or_id).first()
        return (obj, "searchset")
    if k in ("prompt", "prompts"):
        obj = SearchSetItem.objects(id=uuid_or_id, searchtype="prompt").first()
        return (obj, "prompt")
    if k in ("formatter", "formatters"):
        obj = SearchSetItem.objects(id=uuid_or_id, searchtype="formatter").first()
        return (obj, "formatter")
    return (None, None)


def _verification_identifier(kind: str, obj) -> str | None:
    if not obj:
        return None
    if kind == "workflow":
        return str(getattr(obj, "id", None))
    if kind == "searchset":
        return getattr(obj, "uuid", None)
    if kind in {"prompt", "formatter"}:
        return str(getattr(obj, "id", None))
    return str(getattr(obj, "id", None))


def _default_category_for_kind(kind: str) -> str:
    mapping = {
        "workflow": "workflow",
        "searchset": "extraction",
        "prompt": "prompt",
        "formatter": "transform",
    }
    return mapping.get(kind, "workflow")


def _object_title(kind: str, obj) -> str:
    if not obj:
        return ""
    if kind == "workflow":
        return getattr(obj, "name", "") or getattr(obj, "title", "")
    return getattr(obj, "title", "") or getattr(obj, "name", "")


def _object_description(kind: str, obj) -> str:
    if not obj:
        return ""
    if kind == "workflow":
        return getattr(obj, "description", "") or ""
    if kind in {"prompt", "formatter"}:
        return getattr(obj, "searchphrase", "") or ""
    return ""


def _default_version_hash(obj) -> str:
    ts = getattr(obj, "updated_at", None) or getattr(obj, "created_at", None)
    if ts is None:
        return ""
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def _global_examiners() -> list[User]:
    return list(User.objects(is_examiner=True))


def _notify_examiners_of_submission(
    team: Team | None, request: VerificationRequest, submitter: User
) -> None:
    examiners = _global_examiners()
    recipients = [u.user_id for u in examiners if u.user_id != submitter.user_id]
    if not recipients:
        return

    team_name = team.name if team else "Global"
    subject = f"[{team_name}] Verification request submitted"
    link = url_for("library.library_page", scope="verify", _external=True)
    body = (
        "Hi team,\n\n"
        f"{submitter.name or submitter.user_id} submitted '{request.item_title or request.item_kind.title()}'.\n"
        f"Team: {team_name}\n"
        f"Category: {request.category or request.item_kind}\n"
        f"Summary: {request.summary or 'No summary provided.'}\n\n"
        f"Review it here: {link}\n\n"
        "Thank you."
    )

    try:
        msg = Message(subject=subject, recipients=recipients, body=body)
        mail.send(msg)
    except Exception as exc:  # pragma: no cover - best-effort notification
        print(f"Failed to send verification notification: {exc}")


def _notify_team_of_share(
    team: Team,
    obj,
    kind: str,
    added_by: User,
) -> None:
    if not team:
        return

    members = TeamMembership.objects(team=team)
    recipients = {
        m.user_id
        for m in members
        if m.user_id and added_by and m.user_id != added_by.user_id
    }
    if not recipients:
        return

    item_title = _object_title(kind, obj) or "Untitled item"
    category_label = _default_category_for_kind(kind).capitalize()
    link = url_for(
        "home.index",
        section="Library",
        scope="team",
        _external=True,
    )
    actor_name = added_by.name or added_by.user_id
    team_name = team.name or "Team"
    subject = f"[{team_name}] New {category_label} added to the team library"
    body = (
        f"Hi,\n\n"
        f"{actor_name} just added “{item_title}” ({category_label}) to the {team_name} team library.\n\n"
        f"Open the library: {link}\n\n"
        "— Vandalizer"
    )

    try:
        msg = Message(subject=subject, recipients=list(recipients), body=body)
        mail.send(msg)
    except Exception as exc:  # pragma: no cover - best-effort notification
        print(f"Failed to notify team of share: {exc}")


def _format_status_label(status: VerificationStatus | str | None) -> str:
    if isinstance(status, VerificationStatus):
        status = status.value
    if not status:
        return "draft"
    return status.replace("_", " ").title()


def _notify_submitter_of_status_change(
    request_doc: VerificationRequest,
    previous_status: VerificationStatus,
    new_status: VerificationStatus,
    actor: User | None,
) -> None:
    recipient = request_doc.submitter_user_id
    if not recipient:
        return
    if actor and recipient == actor.user_id:
        return
    if previous_status == new_status:
        return

    submitter_name = request_doc.submitter_name or recipient
    actor_name = actor.name if actor and actor.name else (actor.user_id if actor else "A verifier")
    team_name = request_doc.team.name if request_doc.team else "Global"
    item_title = request_doc.item_title or _object_title(request_doc.item_kind, None) or "Your submission"
    previous_label = _format_status_label(previous_status)
    new_label = _format_status_label(new_status)
    link = url_for(
        "home.index",
        section="Library",
        scope="team",
        _external=True,
    )

    subject = f"[{team_name}] Verification status updated: {item_title}"
    body = (
        f"Hi {submitter_name},\n\n"
        f"{actor_name} updated the verification status for “{item_title}”.\n"
        f"Status: {previous_label} → {new_label}\n\n"
        f"You can review the item in the team library here:\n{link}\n\n"
        "— Vandalizer"
    )

    try:
        msg = Message(subject=subject, recipients=[recipient], body=body)
        mail.send(msg)
    except Exception as exc:  # pragma: no cover - best-effort notification
        print(f"Failed to notify submitter of status change: {exc}")


def _build_verification_queue(
    team: Team | None = None, *, restrict_to_team: bool = False
) -> list[dict]:
    pending_statuses = [
        VerificationStatus.SUBMITTED.value,
        VerificationStatus.IN_REVIEW.value,
    ]
    queue: list[dict] = []

    qs = VerificationRequest.objects(status__in=pending_statuses).order_by("-updated_at")
    if restrict_to_team and team:
        qs = qs.filter(team=team)

    requests = list(qs)

    for req in requests:
        obj, kind = _resolve_obj(req.item_kind, req.item_identifier)
        if not obj:
            continue
        title = _object_title(kind, obj) or req.item_title or "(Untitled)"
        queue.append(
            {
                "request": req,
                "data": req.to_public_dict(),
                "kind": kind,
                "identifier": req.item_identifier,
                "title": title,
                "summary": req.summary or "",
                "run_instructions": req.run_instructions or "",
                "submitter": req.submitter_name or req.submitter_user_id,
                "object": obj,
                "team": req.team,
                "team_name": req.team.name if req.team else "",
            }
        )
    return queue


def _coerce_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        lines = value.replace("\r", "\n").split("\n")
        return [line.strip() for line in lines if line.strip()]
    return []


def _coerce_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = value.replace("\r", "\n").replace(",", "\n").split("\n")
    else:
        raw = []
    cleaned = {str(tag).strip() for tag in raw if str(tag).strip()}
    return sorted(cleaned)


def _ensure_verified_li_note(li: LibraryItem, request: VerificationRequest) -> None:
    """
    Store verification request metadata on the LibraryItem for curator dashboards.
    """
    payload = request.to_public_dict()
    li.note = json.dumps(payload)
    tags = set(li.tags or [])
    if payload.get("status") in {"submitted", "in_review"}:
        tags.add("verifying")
    else:
        tags.discard("verifying")
    li.tags = sorted(list(tags))
    li.save()


def _get_or_none_library(
    scope: LibraryScope, *, user: User | None, team: Team | None
) -> Library | None:
    if scope == LibraryScope.PERSONAL:
        if not user:
            return None
        return Library.objects(
            scope=LibraryScope.PERSONAL, owner_user_id=user.user_id
        ).first()
    if scope == LibraryScope.TEAM:
        if not team:
            return None
        return Library.objects(scope=LibraryScope.TEAM, team=team).first()
    if scope == LibraryScope.VERIFIED:
        return Library.objects(scope=LibraryScope.VERIFIED).first()
    return None


def _resolve_scope(scope_str: str) -> LibraryScope:
    """
    Maps UI 'scope' querystrings to your enum.
    UI accepts: 'team' | 'mine' | 'verified'
    """
    scope_str = (scope_str or "").lower()
    if scope_str in ("mine", "personal"):
        return LibraryScope.PERSONAL
    if scope_str == "verified":
        return LibraryScope.VERIFIED
    # default to team
    return LibraryScope.TEAM


# -----------------------------
# Data building for template
# -----------------------------
def _build_results_for_template(filters: dict) -> dict:
    """
    Returns the dict expected by _results.html:
    - workflows
    - extraction_sets
    - prompts
    - formatters
    - scope
    - filters
    """
    scope_in = filters.get("scope") or "team"
    item_type = filters.get("type") or "workflows"
    kinds = filters.get("kinds") or []
    query = (filters.get("q") or "").strip().lower()

    # Resolve library by scope
    user = load_user()
    can_edit_verified = bool(user and user.is_examiner)
    team = _current_team_for_user(user)
    lib_scope = _resolve_scope(scope_in)
    lib = _get_or_none_library(lib_scope, user=user, team=team)
    collections = []
    if lib_scope == LibraryScope.VERIFIED:
        collections = list(VerifiedCollection.objects().order_by("-updated_at"))

    # If there is no library yet, present empty lists gracefully
    # We filter lib_items by folder if applicable
    target_folder_id = filters.get("folderId")
    if target_folder_id == "0":
         target_folder_id = None
         
    # Fetch Folders (subfolders)
    # We need to find folders in this scope that have the given parent_id
    folders = []
    if lib_scope == LibraryScope.PERSONAL and user:
        folders = list(LibraryFolder.objects(scope=LibraryScope.PERSONAL, owner_user_id=user.user_id, parent_id=target_folder_id).order_by("name"))
    elif lib_scope == LibraryScope.TEAM and team:
        folders = list(LibraryFolder.objects(scope=LibraryScope.TEAM, team=team, parent_id=target_folder_id).order_by("name"))
        
    # Get Breadcrumbs
    breadcrumbs = []
    current_folder = None
    if target_folder_id:
        current_folder = LibraryFolder.objects(uuid=target_folder_id).first()
        # Build chain (naive recursive/iterative up)
        curr = current_folder
        while curr:
            breadcrumbs.insert(0, {"name": curr.name, "uuid": curr.uuid})
            if curr.parent_id:
                curr = LibraryFolder.objects(uuid=curr.parent_id).first()
            else:
                curr = None
    
    # Filter items by folder
    # Note: lib.items is a list of references. iterating and dereferencing is expensive if list is huge.
    # But for now we stick to the pattern.
    raw_items = list(lib.items) if lib else []
    lib_items: list[LibraryItem] = []
    
    for li in raw_items:
        # Check folder match
        # li.folder is a ReferenceField. 
        # access checks DB? MongoEngine caches?
        # If li.folder is None, it means root.
        # We need to compare UUIDs safely.
        
        li_folder_id = None
        if li.folder:
             li_folder_id = li.folder.uuid # Assuming we resolve it or it has uuid field
             
        if str(li_folder_id or "") == str(target_folder_id or ""):
             lib_items.append(li)
             
    # If using search (query), we might want to ignore folders and show all matching items?
    # Usually search transcends folders.
    if query:
        # If searching, reset lib_items to ALL items matching query, ignore folder structure?
        # Or search within folder? 
        # Standard UX: Search is global or global-context.
        # Let's search ALL items in library if query exists.
        lib_items = raw_items 
        folders = [] # Hide folders in search mode? Or filter folders?


    # Determine which categories we need to collect & cap counts to avoid massive payloads
    needs_workflows = item_type in ("workflows", "all")
    needs_tasks = item_type in ("tasks", "all")
    wants_extract = needs_tasks and (not kinds or "extract" in kinds)
    wants_prompt = needs_tasks and (not kinds or "prompt" in kinds)
    wants_formatter = needs_tasks and (not kinds or "format" in kinds)

    # --- View-based ID collection ---
    view = filters.get("view") or "all"
    target_ids = set()
    
    user_config = UserModelConfig.objects(user_id=user.user_id).first() if user else None
    
    if view == "pinned" and user_config:
        target_ids = set(user_config.pinned_items)
    elif view == "favorites" and user_config:
        target_ids = set(user_config.favorite_items)
    elif view == "recents" and user:
        # Fetch recent activity for this user
        activities = ActivityEvent.objects(
            user_id=user.user_id, 
            type__in=[ActivityType.WORKFLOW_RUN.value, ActivityType.SEARCH_SET_RUN.value]
        ).order_by("-started_at").limit(50)
        
        # Extract object IDs
        for act in activities:
            if act.workflow:
                target_ids.add(str(act.workflow.id))
            elif act.search_set_uuid:
                target_ids.add(act.search_set_uuid)
    

    needs_map = {
        "workflow": needs_workflows,
        "searchset": wants_extract,
        "prompt": wants_prompt,
        "formatter": wants_formatter,
    }
    limits = {
        "workflow": MAX_LIBRARY_WORKFLOWS if needs_workflows else 0,
        "searchset": MAX_LIBRARY_EXTRACTIONS if wants_extract else 0,
        "prompt": MAX_LIBRARY_PROMPTS if wants_prompt else 0,
        "formatter": MAX_LIBRARY_FORMATTERS if wants_formatter else 0,
    }
    gathered = {k: 0 for k in needs_map}

    # --- Separate polymorphic objects (bounded)
    workflow_objs: list[Workflow] = []
    searchset_objs: list[SearchSet] = []
    prompt_objs: list[SearchSetItem] = []
    formatter_objs: list[SearchSetItem] = []
    verification_keys: dict[str, tuple[str, str]] = {}

    for li in lib_items:
        try:
            obj = (
                li.obj
            )  # <-- this may raise DoesNotExist if the target doc was deleted
        except DoesNotExist:
            li.delete()
            continue

        if not needs_map.get(li.kind, False):
            continue
        
        # --- View Filtering ---
        identifier = _verification_identifier(li.kind, obj)
        
        if view in ("pinned", "favorites", "recents"):
            if identifier not in target_ids:
                continue
        elif view == "created_by_me":
            if li.added_by_user_id != (user.user_id if user else ""):
                continue
        elif view == "shared_with_me":
             if li.added_by_user_id == (user.user_id if user else ""):
                continue
        elif view == "drafts":
             # Check verification status (naive check: unverified)
             if getattr(obj, "verified", False):
                 continue

        if gathered[li.kind] >= limits.get(li.kind, 0):
            # Already have enough of this type
            continue

        # Attach tags from LibraryItem to the object for template rendering
        if hasattr(obj, "tags") and not obj.tags:
             # If mapping exists but empty, or overwrite? 
             # LibraryItem tags are the "organization" tags. 
             # Let's overwrite or transparently set.
             obj.tags = li.tags
        elif not hasattr(obj, "tags"):
             obj.tags = li.tags

        if identifier:
            verification_keys[f"{li.kind}:{identifier}"] = (li.kind, identifier)

        # li.kind is "workflow" or "searchset"
        if li.kind == "workflow" and obj and isinstance(obj, Workflow):
            workflow_objs.append(obj)
            gathered["workflow"] += 1
        elif li.kind == "searchset" and obj and isinstance(obj, SearchSet):
            searchset_objs.append(obj)
            gathered["searchset"] += 1
        elif li.kind == "prompt" and obj and isinstance(obj, SearchSetItem):
            prompt_objs.append(obj)
            gathered["prompt"] += 1
        elif li.kind == "formatter" and obj and isinstance(obj, SearchSetItem):
            formatter_objs.append(obj)
            gathered["formatter"] += 1

        if all(
            (not needs_map[k]) or gathered.get(k, 0) >= limits.get(k, 0)
            for k in needs_map
        ):
            break

    verification_docs: dict[str, VerificationRequest] = {}
    if verification_keys:
        identifiers = [pair[1] for pair in verification_keys.values()]
        kinds_needed = list({pair[0] for pair in verification_keys.values()})
        reqs = VerificationRequest.objects(
            item_identifier__in=identifiers, item_kind__in=kinds_needed
        )
        for req in reqs:
            key = f"{req.item_kind}:{req.item_identifier}"
            existing = verification_docs.get(key)
            if not existing or req.updated_at > existing.updated_at:
                verification_docs[key] = req
    verification_payloads = {
        key: req.to_public_dict() for key, req in verification_docs.items()
    }

    # --- Apply 'type' and 'kinds'
    # type: 'workflows' | 'tasks' | 'all'
    # kinds only affect tasks; in our data model 'extract' maps to SearchSet.set_type == 'extraction'
    # (If you later add Prompt/Formatter collections, wire them similarly.)
    workflows = []
    extraction_sets = []
    prompts = []  # placeholders; not defined in provided model
    formatters = []  # placeholders; not defined in provided model

    # Filter workflows
    if item_type in ("workflows", "all"):
        workflows = workflow_objs

    # Filter task sets (SearchSet) by kind
    if item_type in ("tasks", "all"):
        if wants_extract:
            extraction_sets = [
                s for s in searchset_objs if (s.set_type or "").lower() == "extraction"
            ]
        if wants_prompt:
            prompts = [
                s for s in prompt_objs if (s.searchtype or "").lower() == "prompt"
            ]
        if wants_formatter:
            formatters = [
                s
                for s in formatter_objs
                if (s.searchtype or "").lower() == "formatter"
            ]

    # --- Text search
    if query:
        if workflows:
            workflows = [
                w
                for w in workflows
                if query in (w.name or "").lower()
                or query in (w.description or "").lower()
            ]
        if extraction_sets:
            extraction_sets = [
                s for s in extraction_sets if query in (s.title or "").lower()
            ]
        if prompts:
            prompts = [s for s in prompts if query in (s.title or "").lower()]
        if formatters:
            formatters = [s for s in formatters if query in (s.title or "").lower()]

    # --- Populate Last Run Map (Before sort) ---
    # optimization: only query for items in the final lists (pre-sort, or post-filter?)
    # We need it for sorting if sort='recent'. 
    # But visible_wf_ids depends on the list being filtered (which it is, above).
    
    visible_wf_ids = [str(w.id) for w in workflows]
    visible_ss_uuids = [s.uuid for s in extraction_sets]
    
    last_run_map = {}

    if visible_wf_ids or visible_ss_uuids:
        # Re-using the logic from 'recents' view but broader
        recent_acts = ActivityEvent.objects(
            Q(user_id=user.user_id) if user else Q(id__exists=False), 
            type__in=[ActivityType.WORKFLOW_RUN.value, ActivityType.SEARCH_SET_RUN.value]
        ).order_by("-started_at").limit(200).only("started_at", "workflow", "search_set_uuid")
        
        for act in recent_acts:
            if act.workflow:
                w_id = str(act.workflow.id)
                if w_id not in last_run_map and w_id in visible_wf_ids:
                    last_run_map[w_id] = act.started_at
            if act.search_set_uuid:
                s_id = act.search_set_uuid
                if s_id not in last_run_map and s_id in visible_ss_uuids:
                    last_run_map[s_id] = act.started_at

    # --- Sort
    sort_mode = filters.get("sort") or "updated"
    
    # Helpers for sorting
    def _normalize_dt(value: datetime | None) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _sort_key_workflow(w):
        val = None
        if sort_mode == "recent":
            val = last_run_map.get(str(w.id))
            return _normalize_dt(val)
        elif sort_mode == "az":
            return (w.name or "").lower()
        else: # updated
            return _normalize_dt(w.updated_at or w.created_at)

    def _sort_key_searchset(s):
        val = None
        if sort_mode == "recent":
            val = last_run_map.get(s.uuid)
            return _normalize_dt(val)
        elif sort_mode == "az":
            return (s.title or "").lower()
        else:
            return _normalize_dt(s.updated_at or s.created_at)

    reverse_sort = True
    if sort_mode == "az":
        reverse_sort = False

    workflows.sort(key=_sort_key_workflow, reverse=reverse_sort)
    extraction_sets.sort(key=_sort_key_searchset, reverse=reverse_sort)
    prompts.sort(key=lambda p: (p.title or "").lower(), reverse=(sort_mode!="az"))
    
    # Context
    mixed_items: list[dict[str, Any]] | None = None
    if sort_mode == "az" and item_type == "all":
        def _normalize(entry_kind: str, entry_obj) -> str:
            if entry_kind == "workflow":
                return (entry_obj.name or "").lower()
            if entry_kind == "searchset":
                return (entry_obj.title or "").lower()
            return (entry_obj.title or "").lower()

        candidates: list[dict[str, Any]] = []
        for wf in workflows:
            candidates.append({"kind": "workflow", "obj": wf, "key": _normalize("workflow", wf)})
        for ss in extraction_sets:
            candidates.append({"kind": "searchset", "obj": ss, "key": _normalize("searchset", ss)})
        for p in prompts:
            candidates.append({"kind": "prompt", "obj": p, "key": _normalize("prompt", p)})
        for f in formatters:
            candidates.append({"kind": "formatter", "obj": f, "key": _normalize("formatter", f)})

        candidates.sort(key=lambda entry: entry["key"])
        mixed_items = candidates

    # --- Build verified items list with metadata (for VERIFIED scope) ---
    verified_items_with_meta = []
    if lib_scope == LibraryScope.VERIFIED and lib:
        # Get all items from verified library
        for li in list(lib.items):
            try:
                obj = li.obj
            except DoesNotExist:
                continue
            
            kind = li.kind
            identifier = _verification_identifier(kind, obj)
            if not identifier:
                continue
            
            # Fetch metadata
            meta = VerifiedItemMetadata.objects(
                item_kind=kind, item_identifier=identifier
            ).first()
            
            title = _object_title(kind, obj)
            description = _object_description(kind, obj)
            
            verified_items_with_meta.append({
                "obj": obj,
                "kind": kind,
                "identifier": identifier,
                "title": meta.display_name if meta and meta.display_name else title,
                "description": meta.description if meta and meta.description else description,
                "markdown": meta.markdown if meta else "",
                "category": _default_category_for_kind(kind),
                "library_item_id": str(li.id),
            })
    
    # --- Format collections with item counts ---
    formatted_collections = []
    for coll in collections:
        formatted_collections.append({
            "id": str(coll.id),
            "title": coll.title,
            "description": coll.description or "",
            "promo_image_url": coll.promo_image_url or "",
            "item_count": len(coll.items) if coll.items else 0,
            "updated_at": coll.updated_at,
        })

    context = {
        "workflows": workflows,
        "extraction_sets": extraction_sets,
        "prompts": prompts,
        "formatters": formatters,
        "mixed_items": mixed_items,
        "verification_requests": verification_payloads,
        "collections": formatted_collections,
        "verified_items": verified_items_with_meta,
        "filters": {
            "type": item_type,
            "kinds": kinds,
            "q": query,
            "view": view,
            "sort": sort_mode,
            "displayMode": filters.get("displayMode", "list")
        },
        # expose simple scope used in badges in your _results.html
        "scope": "team"
        if lib_scope == LibraryScope.TEAM
        else ("mine" if lib_scope == LibraryScope.PERSONAL else "verified"),
        "user_pinned": user_config.pinned_items if user_config else [],
        "user_favorites": user_config.favorite_items if user_config else [],
        "can_edit_verified": can_edit_verified,
        "last_run_map": last_run_map,
        "folders": folders,
        "breadcrumbs": breadcrumbs,
        "current_folder_id": target_folder_id,
    }

    return context



@library.route("/manage_verified")
@login_required
def manage_verified():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    verified_lib = get_or_create_verified_library()
    library_items = list(verified_lib.items) if verified_lib else []
    verified_items = []
    item_lookup = {}

    for li in library_items:
        obj = li.obj
        kind = li.kind
        identifier = _verification_identifier(kind, obj)
        if not identifier:
            continue
        meta = VerifiedItemMetadata.objects(
            item_kind=kind, item_identifier=identifier
        ).first()
        title = _object_title(kind, obj)
        description = _object_description(kind, obj)
        payload = {
            "library_item_id": str(li.id),
            "kind": kind,
            "identifier": identifier,
            "title": title,
            "description": description,
            "display_name": meta.display_name if meta else "",
            "meta_description": meta.description if meta else "",
            "markdown": meta.markdown if meta else "",
        }
        verified_items.append(payload)
        item_lookup[str(li.id)] = {
            "title": title,
            "kind": kind,
        }

    collections = list(VerifiedCollection.objects().order_by("-updated_at"))
    verification_queue = _build_verification_queue()
    can_manage_examiners = bool(user.is_admin and user.is_examiner)
    examiner_users = []
    if can_manage_examiners:
        users = list(User.objects())
        users.sort(
            key=lambda u: (
                (u.name or "").lower(),
                (u.email or "").lower(),
                (u.user_id or "").lower(),
            )
        )
        examiner_users = [
            {
                "user_id": u.user_id,
                "label": (
                    f"{u.name} - {u.email} ({u.user_id})"
                    if u.name and u.email
                    else (f"{u.name} ({u.user_id})" if u.name else None)
                    or (f"{u.email} ({u.user_id})" if u.email else None)
                    or u.user_id
                ),
                "is_examiner": bool(u.is_examiner),
            }
            for u in users
        ]

    return render_template(
        "library/manage_verified.html",
        verified_items=verified_items,
        collections=collections,
        item_lookup=item_lookup,
        verification_queue=verification_queue,
        can_manage_examiners=can_manage_examiners,
        examiner_users=examiner_users,
    )


@library.route("/verification/examiners/update", methods=["POST"])
@login_required
def update_examiner_status():
    user = load_user()
    if not user or not user.is_examiner or not user.is_admin:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(force=True) or {}
    target_user_id = (data.get("user_id") or "").strip()
    if not target_user_id:
        return jsonify({"error": "missing user_id"}), 400

    if "is_examiner" not in data:
        return jsonify({"error": "missing is_examiner"}), 400

    target = User.objects(user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "user not found"}), 404

    target.is_examiner = bool(data.get("is_examiner"))
    target.save()

    return jsonify(
        {
            "ok": True,
            "user_id": target.user_id,
            "is_examiner": bool(target.is_examiner),
        }
    )


@library.route("/verified/item/update", methods=["POST"])
@login_required
def update_verified_item_metadata():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(force=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    identifier = (data.get("identifier") or "").strip()
    if not kind or not identifier:
        return jsonify({"error": "missing required fields"}), 400

    meta = VerifiedItemMetadata.objects(
        item_kind=kind, item_identifier=identifier
    ).first()
    if not meta:
        meta = VerifiedItemMetadata(item_kind=kind, item_identifier=identifier)

    meta.display_name = (data.get("display_name") or "").strip()
    meta.description = (data.get("description") or "").strip()
    meta.markdown = (data.get("markdown") or "").strip()
    meta.updated_by_user_id = user.user_id
    meta.save()

    return jsonify({"ok": True})


@library.route("/verified/item/remove", methods=["POST"])
@login_required
def remove_verified_item():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(force=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    identifier = (data.get("identifier") or "").strip()
    if not kind or not identifier:
        return jsonify({"error": "missing required fields"}), 400

    obj, normalized_kind = _resolve_obj(kind, identifier)
    if not obj or not normalized_kind:
        return jsonify({"error": "not found"}), 404

    item_identifier = _verification_identifier(normalized_kind, obj)
    if not item_identifier:
        return jsonify({"error": "identifier not found"}), 400

    verified_lib = get_or_create_verified_library()
    target_li = None
    if verified_lib:
        for li in list(verified_lib.items):
            li_identifier = _verification_identifier(li.kind, li.obj)
            if li.kind == normalized_kind and li_identifier == item_identifier:
                target_li = li
                break

    if target_li:
        verified_lib.items.remove(target_li)
        verified_lib.updated_at = datetime.now(timezone.utc)
        verified_lib.save()
        target_li.delete()

    if hasattr(obj, "verified"):
        setattr(obj, "verified", False)
        obj.save()
        sync_verification_flags_for_object(obj, None)

    req = VerificationRequest.objects(
        item_kind=normalized_kind, item_identifier=item_identifier
    ).first()
    if not req:
        team = _current_team_for_user(user)
        req = VerificationRequest(
            item_kind=normalized_kind,
            item_identifier=item_identifier,
            team=team,
            status=VerificationStatus.SUBMITTED,
            submitter_user_id=user.user_id,
            submitter_name=user.name or user.user_id,
            submitter_org=team.name if team else "",
            submitter_role=user.role_in_team(team) if team else "",
            item_title=_object_title(normalized_kind, obj) or item_identifier,
            item_version_hash=_default_version_hash(obj),
            category=_default_category_for_kind(normalized_kind),
            summary="Moved from verified catalog for re-review.",
        )
    else:
        req.status = VerificationStatus.SUBMITTED

    req.library_item = None
    req.save()

    return jsonify({"ok": True, "status": req.status.value})


@library.route("/verified/item/send_to_user", methods=["POST"])
@login_required
def send_verified_item_to_user():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(force=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    identifier = (data.get("identifier") or "").strip()
    recipient = (data.get("recipient") or "").strip()
    if not kind or not identifier or not recipient:
        return jsonify({"error": "missing required fields"}), 400

    recipient_user = User.objects(Q(user_id=recipient) | Q(email=recipient)).first()
    if not recipient_user:
        return jsonify({"error": "user not found"}), 404

    obj, normalized_kind = _resolve_obj(kind, identifier)
    if not obj or not normalized_kind:
        return jsonify({"error": "item not found"}), 404

    lib = get_or_create_personal_library(recipient_user.user_id)
    li = add_object_to_library(obj, lib, added_by_user_id=user.user_id)
    return jsonify(
        {
            "ok": True,
            "added": bool(li),
            "recipient": recipient_user.user_id,
        }
    )


@library.route("/verified/collections", methods=["POST"])
@login_required
def create_verified_collection():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or request.form or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400

    collection = VerifiedCollection(
        title=title,
        description=(data.get("description") or "").strip(),
        promo_image_url=(data.get("promo_image_url") or "").strip(),
        created_by_user_id=user.user_id,
    )
    collection.save()
    return jsonify({"ok": True, "id": str(collection.id)})


@library.route("/verified/collections/<collection_id>/update", methods=["POST"])
@login_required
def update_verified_collection(collection_id: str):
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    collection = VerifiedCollection.objects(id=collection_id).first()
    if not collection:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or request.form or {}
    title = (data.get("title") or "").strip()
    if title:
        collection.title = title
    collection.description = (data.get("description") or "").strip()
    collection.promo_image_url = (data.get("promo_image_url") or "").strip()
    collection.save()
    return jsonify({"ok": True})


@library.route("/verified/collections/<collection_id>/items/add", methods=["POST"])
@login_required
def add_verified_collection_item(collection_id: str):
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    collection = VerifiedCollection.objects(id=collection_id).first()
    if not collection:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True) or {}
    item_id = (data.get("library_item_id") or "").strip()
    if not item_id:
        return jsonify({"error": "library_item_id required"}), 400

    li = LibraryItem.objects(id=item_id).first()
    if not li:
        return jsonify({"error": "library item not found"}), 404

    if li not in collection.items:
        collection.items.append(li)
        collection.save()

    return jsonify({"ok": True})


@library.route("/verified/collections/<collection_id>/items/remove", methods=["POST"])
@login_required
def remove_verified_collection_item(collection_id: str):
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    collection = VerifiedCollection.objects(id=collection_id).first()
    if not collection:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True) or {}
    item_id = (data.get("library_item_id") or "").strip()
    if not item_id:
        return jsonify({"error": "library_item_id required"}), 400

    li = LibraryItem.objects(id=item_id).first()
    if not li:
        return jsonify({"error": "library item not found"}), 404

    if li in collection.items:
        collection.items.remove(li)
        collection.save()

    return jsonify({"ok": True})


# -----------------------------
# Verified Catalog Exploration Routes
# -----------------------------
@library.route("/collection/<collection_id>", methods=["GET"])
@login_required
def get_collection_details(collection_id):
    """Fetch detailed information about a specific collection."""
    try:
        collection = VerifiedCollection.objects(id=collection_id).first()
        if not collection:
            return jsonify({"error": "Collection not found"}), 404
        
        # Build list of items in this collection
        items_data = []
        for li in collection.items:
            try:
                obj = li.obj
            except DoesNotExist:
                continue
            
            kind = li.kind
            identifier = _verification_identifier(kind, obj)
            if not identifier:
                continue
            
            # Fetch metadata
            meta = VerifiedItemMetadata.objects(
                item_kind=kind, item_identifier=identifier
            ).first()
            
            title = _object_title(kind, obj)
            description = _object_description(kind, obj)
            
            items_data.append({
                "kind": kind,
                "identifier": identifier,
                "title": meta.display_name if meta and meta.display_name else title,
                "description": meta.description if meta and meta.description else description,
                "category": _default_category_for_kind(kind),
                "library_item_id": str(li.id),
            })
        
        return jsonify({
            "ok": True,
            "collection": {
                "id": str(collection.id),
                "title": collection.title,
                "description": collection.description or "",
                "promo_image_url": collection.promo_image_url or "",
                "items": items_data,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@library.route("/verified_item/metadata", methods=["POST"])
@login_required
def get_verified_item_metadata():
    """Fetch metadata for a verified item."""
    data = request.get_json(force=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    identifier = (data.get("identifier") or "").strip()
    
    if not kind or not identifier:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Fetch the actual object to get basic info
    obj, normalized_kind = _resolve_obj(kind, identifier)
    if not obj:
        return jsonify({"error": "Item not found"}), 404
    
    # Fetch metadata if available
    meta = VerifiedItemMetadata.objects(
        item_kind=normalized_kind, item_identifier=identifier
    ).first()
    
    # Fetch verification request if available
    verification_req = VerificationRequest.objects(
        item_kind=normalized_kind, item_identifier=identifier
    ).first()
    
    title = _object_title(normalized_kind, obj)
    description = _object_description(normalized_kind, obj)
    
    result = {
        "kind": normalized_kind,
        "identifier": identifier,
        "title": meta.display_name if meta and meta.display_name else title,
        "description": meta.description if meta and meta.description else description,
        "markdown": meta.markdown if meta else "",
        "category": _default_category_for_kind(normalized_kind),
    }
    
    # Add verification request data if available
    if verification_req:
        result.update({
            "example_inputs": verification_req.example_inputs or [],
            "test_files": verification_req.test_files or [],
            "expected_outputs": verification_req.expected_outputs or [],
            "dependencies": verification_req.dependencies or [],
            "run_instructions": verification_req.run_instructions or "",
            "known_limitations": verification_req.known_limitations or "",
        })
    
    return jsonify({"ok": True, "metadata": result})


@library.route("/verified_item/add_to_library", methods=["POST"])
@login_required
def add_verified_item_to_library():
    """Add a verified item to the user's personal or team library."""
    user = load_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json(force=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    identifier = (data.get("identifier") or "").strip()
    scope_str = (data.get("scope") or "personal").strip().lower()
    
    if not kind or not identifier:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Resolve the object
    obj, normalized_kind = _resolve_obj(kind, identifier)
    if not obj:
        return jsonify({"error": "Item not found"}), 404
    
    # Determine target library
    if scope_str in ("personal", "mine"):
        target_lib = get_or_create_personal_library(user.user_id)
    elif scope_str == "team":
        team = _current_team_for_user(user)
        if not team:
            return jsonify({"error": "No active team"}), 400
        target_lib = get_or_create_team_library(team)
    else:
        return jsonify({"error": "Invalid scope"}), 400
    
    # Check if already in library
    existing = LibraryItem.objects(obj=obj, kind=normalized_kind).first()
    if existing and existing in target_lib.items:
        return jsonify({"ok": True, "message": "Item already in library", "added": False})
    
    # Add to library
    try:
        add_object_to_library(
            obj,
            normalized_kind,
            user.user_id,
            target_lib
        )
        return jsonify({"ok": True, "message": "Item added to library", "added": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Routes
# -----------------------------
@library.route("/")
def library_page():
    """
    Renders the main library page.
    Initial state is determined by URL query parameters.
    """
    user = load_user()
    can_verify = bool(user and user.is_examiner)
    # Get initial state from URL or set defaults
    scope = request.args.get("scope", "team")  # 'team' | 'mine' | 'verified'
    item_type = request.args.get("type", "workflows")  # 'workflows' | 'tasks' | 'all'
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = [k for k in kinds_str.split(",") if k] if kinds_str else []
    query = request.args.get("q", "")

    if scope == "verify" and not can_verify:
        scope = "team"

    return render_template(
        "index.html",  # your main page template
        scope=scope,
        item_type=item_type,
        kinds=kinds,
        query=query,
        initial_library_results="",
        can_verify=can_verify,
    )


@library.route("/filter", methods=["POST"])
@login_required
@validate_json_request()
def filter_library_items():
    """
    AJAX endpoint to fetch filtered results.
    Returns rendered HTML as a JSON object.
    """
    filters = request.get_json() or {}
    ctx = _build_results_for_template(filters)
    
    # Also fetch "Sidebar" folders (Roots for the current scope)
    # We want to show the top-level structure in the sidebar.
    # We can reuse logic or just query roots.
    # Scope logic matches _build_results_for_template.
    
    scope_in = filters.get("scope") or "team"
    lib_scope = _resolve_scope(scope_in)
    user = load_user()
    team = _current_team_for_user(user)
    
    sidebar_folders_data = []
    # Only fetch if we are in a folder-supporting scope
    if lib_scope in (LibraryScope.PERSONAL, LibraryScope.TEAM):
        # Fetch ALL folders or just roots? 
        # Ideally a tree, but let's start with Roots + lazy load or just Roots. 
        # User said "folders section", implying a list.
        # Let's return ALL folders for now so we can build a client-side tree or flat list?
        # Or just Roots for now. "Folders" usually implies the top level buckets.
        
        # ACTUALLY: Sidebar usually shows the full tree or at least roots.
        # Let's fetch roots (parent_id=None).
        
        q_kwargs = {"scope": lib_scope, "parent_id": None}
        if lib_scope == LibraryScope.PERSONAL:
             q_kwargs["owner_user_id"] = user.user_id
        elif lib_scope == LibraryScope.TEAM:
             q_kwargs["team"] = team
             
        roots = LibraryFolder.objects(**q_kwargs).order_by("name")
        sidebar_folders_data = [{"name": f.name, "uuid": f.uuid} for f in roots]

    if scope_in == "verify":
        rendered_html = render_template("library/_verification_queue.html", requests=ctx.get("verification_queue"), team=team)
    else:
        rendered_html = render_template("library/_results.html", **ctx)
    
    return jsonify({
        "template": rendered_html,
        "sidebar_folders": sidebar_folders_data
    })


@library.route("/verification/queue", methods=["POST"])
def verification_queue():
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    queue = _build_verification_queue()
    rendered_html = render_template(
        "library/_verification_queue.html",
        requests=queue,
        team=None,
    )
    return jsonify({"template": rendered_html})


@library.route("/verification/request", methods=["GET"])
def get_verification_request():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    kind = request.args.get("kind", "")
    uuid = request.args.get("uuid", "")
    obj, normalized_kind = _resolve_obj(kind, uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    identifier = _verification_identifier(normalized_kind, obj)
    if not identifier:
        return jsonify({"error": "unsupported"}), 400

    request_doc = VerificationRequest.objects(
        item_kind=normalized_kind, item_identifier=identifier
    ).first()

    team = _current_team_for_user(user)
    default_payload = {
        "item_kind": normalized_kind,
        "item_identifier": identifier,
        "status": VerificationStatus.DRAFT.value,
        "submitter_user_id": user.user_id,
        "submitter_name": user.name or user.user_id,
        "submitter_org": team.name if team else "",
        "submitter_role": user.role_in_team(team) or "",
        "item_title": _object_title(normalized_kind, obj),
        "item_version_hash": _default_version_hash(obj),
        "category": _default_category_for_kind(normalized_kind),
        "summary": "",
        "description": "",
        "example_inputs": [],
        "test_files": [],
        "expected_outputs": [],
        "dependencies": [],
        "run_instructions": "",
        "known_limitations": "",
        "intended_use_tags": [],
        "evaluation_notes": "",
    }

    if request_doc:
        payload = default_payload | request_doc.to_public_dict()
        status = payload.get("status", VerificationStatus.SUBMITTED.value)
        editable = status not in {VerificationStatus.APPROVED.value}
    else:
        payload = default_payload
        status = payload["status"]
        editable = True

    return jsonify(
        {
            "ok": True,
            "data": payload,
            "status": status,
            "editable": editable,
            "is_verified": bool(getattr(obj, "verified", False)),
            "request_uuid": payload.get("uuid"),
        }
    )


# -----------------------------
# Fork helpers
# -----------------------------
def _fork_workflow(obj: Workflow, *, user_id: str) -> Workflow:
    new_steps = []
    for step in obj.steps or []:
        new_tasks = []
        for task in step.tasks or []:
            task_data = deepcopy(task.data) if task.data else {}
            dup_task = WorkflowStepTask(name=task.name, data=task_data).save()
            new_tasks.append(dup_task)

        step_data = deepcopy(step.data) if step.data else None
        dup_step = WorkflowStep(name=step.name, tasks=new_tasks, data=step_data).save()
        new_steps.append(dup_step)

    new_atts = []
    for att in obj.attachments or []:
        dup_att = WorkflowAttachment(attachment=att.attachment).save()
        new_atts.append(dup_att)

    return Workflow(
        name=obj.name,
        description=obj.description,
        user_id=user_id,
        space=getattr(obj, "space", None),
        steps=new_steps,
        attachments=new_atts,
        verified=False,
        created_by_user_id=user_id,
    ).save()


def _fork_searchset(obj: SearchSet, *, user_id: str) -> SearchSet:
    new_search_set = SearchSet(
        title=obj.title,
        uuid=uuid.uuid4().hex,
        space=obj.space,
        status=obj.status,
        set_type=obj.set_type,
        user_id=user_id,
        is_global=False,
        user=getattr(obj, "user", None),
        fillable_pdf_url=getattr(obj, "fillable_pdf_url", None),
        verified=False,
        created_by_user_id=user_id,
    ).save()

    for item in obj.items():
        SearchSetItem(
            searchphrase=item.searchphrase,
            searchset=new_search_set.uuid,
            searchtype=item.searchtype,
            text_blocks=item.text_blocks,
            pdf_binding=item.pdf_binding,
            user_id=user_id,
            space_id=item.space_id,
            title=item.title,
        ).save()

    return new_search_set


def _fork_searchset_item(item: SearchSetItem, *, user_id: str) -> SearchSetItem:
    return SearchSetItem(
        searchphrase=item.searchphrase,
        searchset=item.searchset,
        searchtype=item.searchtype,
        text_blocks=item.text_blocks,
        pdf_binding=item.pdf_binding,
        user_id=user_id,
        space_id=item.space_id,
        title=item.title,
    ).save()


# -----------------------------
# Share with my team
# -----------------------------
@library.route("/workflows/share_to_team", methods=["POST"])
def workflows_share_to_team():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    if not team:
        return jsonify({"error": "no team"}), 400

    # ensure membership
    if not TeamMembership.objects(team=team, user_id=user.user_id).first():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, kind = _resolve_obj("workflow", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_workflow(obj, user_id=user.user_id)
    lib = get_or_create_team_library(team)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)

    _notify_team_of_share(team, forked, kind, user)

    return jsonify({"ok": True})


@library.route("/workflows/clone_to_mine", methods=["POST"])
def workflows_clone_to_mine():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, _kind = _resolve_obj("workflow", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_workflow(obj, user_id=user.user_id)
    lib = get_or_create_personal_library(user.user_id)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)
    
    return jsonify({"ok": True, "uuid": str(forked.id)})


@library.route("/extractions/clone_to_mine", methods=["POST"])
def extractions_clone_to_mine():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, _kind = _resolve_obj("extraction", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset(obj, user_id=user.user_id)
    lib = get_or_create_personal_library(user.user_id)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)

    return jsonify({"ok": True, "uuid": forked.uuid})


@library.route("/prompts/clone_to_mine", methods=["POST"])
def prompts_clone_to_mine():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, _kind = _resolve_obj("prompt", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset_item(obj, user_id=user.user_id)
    lib = get_or_create_personal_library(user.user_id)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)

    return jsonify({"ok": True, "uuid": forked.uuid})


@library.route("/formatters/clone_to_mine", methods=["POST"])
def formatters_clone_to_mine():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, _kind = _resolve_obj("formatter", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset_item(obj, user_id=user.user_id)
    lib = get_or_create_personal_library(user.user_id)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)

    return jsonify({"ok": True, "uuid": forked.uuid})


@library.route("/pin", methods=["POST"])
@login_required
@validate_json_request()
def toggle_pin():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json() or {}
    item_uuid = payload.get("uuid")
    if not item_uuid:
        return jsonify({"error": "missing uuid"}), 400

    config = UserModelConfig.objects(user_id=user.user_id).first()
    if not config:
        config = UserModelConfig(user_id=user.user_id, name=user.name or "User").save()

    if item_uuid in config.pinned_items:
        config.pinned_items.remove(item_uuid)
        action = "removed"
    else:
        config.pinned_items.append(item_uuid)
        action = "added"
    
    config.save()
    return jsonify({"ok": True, "action": action})


@library.route("/favorite", methods=["POST"])
@login_required
@validate_json_request()
def toggle_favorite():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json() or {}
    item_uuid = payload.get("uuid")
    if not item_uuid:
        return jsonify({"error": "missing uuid"}), 400

    config = UserModelConfig.objects(user_id=user.user_id).first()
    if not config:
        config = UserModelConfig(user_id=user.user_id, name=user.name or "User").save()

    if item_uuid in config.favorite_items:
        config.favorite_items.remove(item_uuid)
        action = "removed"
    else:
        config.favorite_items.append(item_uuid)
        action = "added"
    
    config.save()
    return jsonify({"ok": True, "action": action})


@library.route("/extractions/share_to_team", methods=["POST"])
def extractions_share_to_team():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    if not team:
        return jsonify({"error": "no team"}), 400

    if not TeamMembership.objects(team=team, user_id=user.user_id).first():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, kind = _resolve_obj("extraction", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset(obj, user_id=user.user_id)
    lib = get_or_create_team_library(team)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)
    _notify_team_of_share(team, forked, kind, user)
    return jsonify({"ok": True})


@library.route("/prompts/share_to_team", methods=["POST"])
def prompts_share_to_team():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    if not team:
        return jsonify({"error": "no team"}), 400

    if not TeamMembership.objects(team=team, user_id=user.user_id).first():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, kind = _resolve_obj("prompt", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset_item(obj, user_id=user.user_id)
    lib = get_or_create_team_library(team)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)
    _notify_team_of_share(team, forked, kind, user)
    return jsonify({"ok": True})


@library.route("/formatters/share_to_team", methods=["POST"])
def formatters_share_to_team():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    if not team:
        return jsonify({"error": "no team"}), 400

    if not TeamMembership.objects(team=team, user_id=user.user_id).first():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    obj, kind = _resolve_obj("formatter", uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    forked = _fork_searchset_item(obj, user_id=user.user_id)
    lib = get_or_create_team_library(team)
    add_object_to_library(forked, lib, added_by_user_id=user.user_id)
    _notify_team_of_share(team, forked, kind, user)
    return jsonify({"ok": True})


@library.route("/remove", methods=["POST"])
@login_required
@validate_json_request()
def remove_library_item():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    payload = request.get_json() or {}
    uuid = payload.get("uuid")
    kind = payload.get("kind")
    scope = payload.get("scope") or "team"

    if not uuid or not kind:
        return jsonify({"error": "invalid request"}), 400

    obj, normalized_kind = _resolve_obj(kind, uuid)
    if not obj or not normalized_kind:
        return jsonify({"error": "not found"}), 404

    # Resolve target library
    target_lib = None
    if scope in ("mine", "personal"):
        target_lib = get_or_create_personal_library(user.user_id)
    else:
        # Default to team
        team = _current_team_for_user(user)
        if not team:
            return jsonify({"error": "no team"}), 400
        # Check membership
        membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
        if not membership:
            return jsonify({"error": "forbidden"}), 403
        
        target_lib = get_or_create_team_library(team)

    if not target_lib:
        return jsonify({"error": "library not found"}), 404

    # Find item in library
    target_item = None
    for item in list(target_lib.items):
        if item.kind == normalized_kind and item.obj == obj:
            target_item = item
            break

    if not target_item:
        # It's possible the item isn't in the library but user wants to delete it? 
        # For now, assume success if it's already gone from the library view.
        return jsonify({"ok": True, "removed": False}), 200

    # Remove from library list
    target_lib.items.remove(target_item)
    target_lib.updated_at = datetime.now(timezone.utc)
    target_lib.save()
    
    # Delete the LibraryItem document itself (cleanup)
    target_item.delete()

    return jsonify({"ok": True, "removed": True})


# -----------------------------
# Submit to be verified
# -----------------------------
@library.route("/workflows/submit_for_verification", methods=["POST"])
def workflows_submit_for_verification():
    return _submit_for_verification_route("workflow")


@library.route("/extractions/submit_for_verification", methods=["POST"])
def extractions_submit_for_verification():
    return _submit_for_verification_route("extraction")


@library.route("/prompts/submit_for_verification", methods=["POST"])
def prompts_submit_for_verification():
    return _submit_for_verification_route("prompt")


@library.route("/formatters/submit_for_verification", methods=["POST"])
def formatters_submit_for_verification():
    return _submit_for_verification_route("formatter")


@library.route("/verification/<request_uuid>/status", methods=["POST"])
def update_verification_status(request_uuid: str):
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    req = VerificationRequest.objects(uuid=request_uuid).first()
    if not req:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True) or {}
    status_str = (data.get("status") or "").strip().lower()
    status_map = {
        "submitted": VerificationStatus.SUBMITTED,
        "in_review": VerificationStatus.IN_REVIEW,
        "approved": VerificationStatus.APPROVED,
        "rejected": VerificationStatus.REJECTED,
    }
    if status_str not in status_map:
        return jsonify({"error": "invalid status"}), 400

    new_status = status_map[status_str]
    previous_status = req.status
    req.status = new_status
    req.save()

    obj, kind = _resolve_obj(req.item_kind, req.item_identifier)
    li = req.library_item
    now = datetime.now(timezone.utc)

    if new_status == VerificationStatus.APPROVED:
        if not obj:
            return jsonify({"error": "item not found"}), 404

        verified_lib = get_or_create_verified_library()
        li = add_object_to_library(obj, verified_lib, added_by_user_id=user.user_id)
        req.library_item = li
        req.save()

        if hasattr(obj, "verified"):
            setattr(obj, "verified", True)
            obj.save()
            sync_verification_flags_for_object(obj, user.user_id)
        if li:
            li.verified = True
            li.verified_at = now
            li.verified_by_user_id = user.user_id
            li.save()
    elif new_status == VerificationStatus.REJECTED:
        if hasattr(obj, "verified"):
            setattr(obj, "verified", False)
            obj.save()
            sync_verification_flags_for_object(obj, None)
        if li:
            li.verified = False
            li.verified_at = None
            li.verified_by_user_id = None
            li.save()

    if li:
        _ensure_verified_li_note(li, req)

    _notify_submitter_of_status_change(req, previous_status, new_status, user)

    return jsonify({"ok": True, "status": req.status.value})


@library.route("/verification/<request_uuid>/remove", methods=["POST"])
@login_required
def remove_verification_request(request_uuid: str):
    user = load_user()
    if not user or not user.is_examiner:
        return jsonify({"error": "forbidden"}), 403

    req = VerificationRequest.objects(uuid=request_uuid).first()
    if not req:
        return jsonify({"error": "not found"}), 404

    if req.status not in {VerificationStatus.SUBMITTED, VerificationStatus.IN_REVIEW}:
        return jsonify({"error": "cannot remove non-pending request"}), 400

    obj, _kind = _resolve_obj(req.item_kind, req.item_identifier)
    if obj and hasattr(obj, "verified"):
        setattr(obj, "verified", False)
        obj.save()
        sync_verification_flags_for_object(obj, None)

    li = req.library_item
    if li:
        verified_lib = get_or_create_verified_library()
        if verified_lib and li in verified_lib.items:
            verified_lib.items.remove(li)
            verified_lib.updated_at = datetime.now(timezone.utc)
            verified_lib.save()
        li.delete()
        req.library_item = None

    req.delete()
    return jsonify({"ok": True})


@library.route("/verification/upload_test_files", methods=["POST"])
@login_required
def upload_verification_test_files():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        return jsonify({"error": "no files uploaded"}), 400

    upload_dir = (
        Path(current_app.root_path)
        / "static"
        / "uploads"
        / str(user.user_id)
        / "verification"
    )
    upload_dir.mkdir(parents=True, exist_ok=True)

    files_payload = []
    for f in uploaded_files:
        if not f or not f.filename:
            continue

        original_name = secure_filename(f.filename)
        if not original_name:
            continue

        stored_name = f"{uuid.uuid4().hex}_{original_name}"
        destination = upload_dir / stored_name
        f.save(str(destination))

        relative_path = f"uploads/{user.user_id}/verification/{stored_name}"
        files_payload.append(
            {
                "original_name": original_name,
                "stored_name": stored_name,
                "path": relative_path,
                "download_url": url_for("static", filename=relative_path),
            }
        )

    if not files_payload:
        return jsonify({"error": "no valid files uploaded"}), 400

    return jsonify({"ok": True, "files": files_payload})


def _submit_for_verification_route(kind: str):
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    form = payload.get("form", {}) or {}

    obj, normalized_kind = _resolve_obj(kind, uuid)
    if not obj:
        return jsonify({"error": "not found"}), 404

    identifier = _verification_identifier(normalized_kind, obj)
    if not identifier:
        return jsonify({"error": "unsupported"}), 400

    existing_request = VerificationRequest.objects(
        item_kind=normalized_kind, item_identifier=identifier
    ).first()

    if existing_request:
        different_submitter = (
            existing_request.submitter_user_id
            and existing_request.submitter_user_id != user.user_id
        )
        if different_submitter and not getattr(user, "is_admin", False):
            return jsonify({"error": "forbidden"}), 403
        request_doc = existing_request
    else:
        request_doc = VerificationRequest(
            item_kind=normalized_kind,
            item_identifier=identifier,
            submitter_user_id=user.user_id,
            item_title=_object_title(normalized_kind, obj) or (form.get("item_title") or ""),
        )

    request_doc.submitter_user_id = user.user_id
    request_doc.submitter_name = (
        form.get("submitter_name")
        or request_doc.submitter_name
        or user.name
        or user.user_id
    )
    request_doc.submitter_org = (
        form.get("submitter_org")
        or request_doc.submitter_org
        or (team.name if team else "")
    )
    request_doc.submitter_role = (
        form.get("submitter_role")
        or request_doc.submitter_role
        or (user.role_in_team(team) if team else "")
    )

    request_doc.item_title = (
        form.get("item_title")
        or request_doc.item_title
        or _object_title(normalized_kind, obj)
    )
    request_doc.item_version_hash = (
        form.get("item_version_hash")
        or request_doc.item_version_hash
        or _default_version_hash(obj)
    )
    request_doc.category = form.get("category") or request_doc.category or _default_category_for_kind(normalized_kind)
    request_doc.summary = (form.get("summary") or "").strip()
    request_doc.description = (form.get("description") or "").strip()
    request_doc.example_inputs = _coerce_string_list(form.get("example_inputs"))
    incoming_test_files = form.get("test_files")
    if isinstance(incoming_test_files, list):
        cleaned_test_files = []
        for file_entry in incoming_test_files:
            if not isinstance(file_entry, dict):
                continue
            original_name = (file_entry.get("original_name") or "").strip()
            stored_name = (file_entry.get("stored_name") or "").strip()
            path = (file_entry.get("path") or "").strip()
            download_url = (file_entry.get("download_url") or "").strip()
            if not path or not download_url:
                continue
            cleaned_test_files.append(
                {
                    "original_name": original_name,
                    "stored_name": stored_name,
                    "path": path,
                    "download_url": download_url,
                }
            )
        request_doc.test_files = cleaned_test_files
    request_doc.expected_outputs = _coerce_string_list(form.get("expected_outputs"))
    if "dependencies" in form:
        request_doc.dependencies = _coerce_string_list(form.get("dependencies"))
    request_doc.run_instructions = (form.get("run_instructions") or "").strip()
    if "known_limitations" in form:
        request_doc.known_limitations = (form.get("known_limitations") or "").strip()
    if "intended_use_tags" in form:
        request_doc.intended_use_tags = _coerce_tags(form.get("intended_use_tags"))
    request_doc.evaluation_notes = (form.get("evaluation_notes") or "").strip()

    request_doc.team = team or request_doc.team

    if not request_doc.status or request_doc.status in {
        VerificationStatus.DRAFT,
        VerificationStatus.REJECTED,
    }:
        request_doc.status = VerificationStatus.SUBMITTED

    verified_lib = get_or_create_verified_library()
    li = add_object_to_library(obj, verified_lib, added_by_user_id=user.user_id)
    if li:
        request_doc.library_item = li

    request_doc.save()

    if li:
        _ensure_verified_li_note(li, request_doc)

    _notify_examiners_of_submission(team, request_doc, user)

    response_payload = request_doc.to_public_dict()
    return jsonify(
        {
            "ok": True,
            "library_item_id": str(li.id) if li else None,
            "verification_request": response_payload,
            "status": response_payload.get("status"),
            "redirect_url": url_for("home.index", scope="mine"),
        }
    )

# -----------------------------
# Folder Management Routes
# -----------------------------

@library.route("/folder/create", methods=["POST"])
@login_required
@validate_json_request()
def create_folder():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401
    
    payload = request.get_json()
    name = payload.get("name")
    parent_id = payload.get("parent_id") # Optional uuid
    scope_str = payload.get("scope", "personal")
    
    if not name:
        return jsonify({"error": "name required"}), 400
        
    # Resolve Scope
    try:
        scope = _resolve_scope(scope_str)
    except ValueError:
        return jsonify({"error": "invalid scope"}), 400

    team = None
    owner_user_id = None
    
    if scope == LibraryScope.PERSONAL:
        owner_user_id = user.user_id
    elif scope == LibraryScope.TEAM:
        team = _current_team_for_user(user)
        if not team:
            return jsonify({"error": "no team context"}), 400
    else:
        return jsonify({"error": "invalid scope for folders"}), 400

    # Create
    folder = LibraryFolder(
        name=name,
        parent_id=parent_id,
        scope=scope,
        owner_user_id=owner_user_id,
        team=team
    )
    folder.save()
    
    return jsonify({"ok": True, "folder": {
        "uuid": folder.uuid,
        "name": folder.name
    }})

@library.route("/folder/delete", methods=["POST"])
@login_required
@validate_json_request()
def delete_folder():
    """
    Deletes a folder. 
    Options: 
    - delete contents (recursive) - NOT IMPLEMENTED YET, items move to root or fail?
    - currently: move items to parent (or root) automatically? 
      Strict implementation: Delete reference in items.
    """
    user = load_user()
    payload = request.get_json()
    folder_uuid = payload.get("uuid")
    
    if not folder_uuid:
        return jsonify({"error": "uuid required"}), 400
        
    folder = LibraryFolder.objects(uuid=folder_uuid).first()
    if not folder:
        return jsonify({"error": "not found"}), 404
        
    # Auth check
    if folder.scope == LibraryScope.PERSONAL:
        if folder.owner_user_id != user.user_id:
            return jsonify({"error": "forbidden"}), 403
    elif folder.scope == LibraryScope.TEAM:
        # TODO: checking team permissions? Assuming members can manage folders for now
        team = _current_team_for_user(user)
        if not team or folder.team != team:
             return jsonify({"error": "forbidden"}), 403
             
    # Logic: Unassign items from this folder (move to root of same library)
    # Alternatively: Delete items? Safest is unassign folder.
    LibraryItem.objects(folder=folder).update(set__folder=None)
    
    # Subfolders? Move to parent
    LibraryFolder.objects(parent_id=folder.uuid).update(set__parent_id=folder.parent_id)
    
    folder.delete()
    return jsonify({"ok": True})

@library.route("/folder/rename", methods=["POST"])
@login_required
@validate_json_request()
def rename_folder():
    user = load_user()
    payload = request.get_json()
    folder_uuid = payload.get("uuid")
    new_name = payload.get("name")
    
    if not folder_uuid or not new_name:
        return jsonify({"error": "uuid and name required"}), 400
        
    folder = LibraryFolder.objects(uuid=folder_uuid).first()
    if not folder:
        return jsonify({"error": "not found"}), 404
        
    # Auth check
    if folder.scope == LibraryScope.PERSONAL:
        if folder.owner_user_id != user.user_id:
            return jsonify({"error": "forbidden"}), 403
    elif folder.scope == LibraryScope.TEAM:
        team = _current_team_for_user(user)
        if not team or folder.team != team:
             return jsonify({"error": "forbidden"}), 403
             
    folder.name = new_name
    folder.save()
    return jsonify({"ok": True})

@library.route("/folder/move_items", methods=["POST"])
@login_required
@validate_json_request()
def move_items_to_folder():
    """
    Moves list of library items (by item identifiers or LibraryItem IDs?) 
    Client likely sends [kind, id] pairs or LibraryItem UUIDs?
    Given existing API structure, better to send library item IDs if known, 
    but UI often deals with [kind, uuid].
    Let's assume payload: items: [{kind, uuid}], target_folder_uuid (or null for root)
    """
    user = load_user()
    payload = request.get_json()
    items_meta = payload.get("items", []) # List of {kind, uuid}
    target_folder_uuid = payload.get("target_folder_uuid")
    scope_str = payload.get("scope")
    intent_scope = _resolve_scope(scope_str) if scope_str else None

    target_folder = None
    if target_folder_uuid:
        target_folder = LibraryFolder.objects(uuid=target_folder_uuid).first()
        if not target_folder:
            return jsonify({"error": "target folder not found"}), 404
            
    # Resolve items and update
    count = 0
    for meta in items_meta:
        kind = meta.get("kind")
        uuid = meta.get("uuid")
        
        obj, normalized_kind = _resolve_obj(kind, uuid)
        if not obj: 
            continue
            
        candidates = LibraryItem.objects(obj=obj, kind=normalized_kind)
        target_li = None
        
        for c in candidates:
             # Find which library contains this item
             parent_lib = Library.objects(items=c).first()
             if not parent_lib: 
                 continue
                 
             if target_folder:
                 # Match target folder's library context
                 if parent_lib.scope == target_folder.scope:
                      if parent_lib.scope == LibraryScope.PERSONAL and parent_lib.owner_user_id == target_folder.owner_user_id:
                            target_li = c
                            break
                      if parent_lib.scope == LibraryScope.TEAM and parent_lib.team == target_folder.team:
                            target_li = c
                            break
             elif intent_scope:
                 # Moving to root, match intent scope
                 if parent_lib.scope == intent_scope:
                      if intent_scope == LibraryScope.PERSONAL and parent_lib.owner_user_id == user.user_id:
                           target_li = c
                           break
                      if intent_scope == LibraryScope.TEAM:
                           current_team = _current_team_for_user(user)
                           if parent_lib.team == current_team:
                                target_li = c
                                break
        
        if target_li:
            target_li.folder = target_folder
            target_li.save()
            count += 1
            
    return jsonify({"ok": True, "count": count})
