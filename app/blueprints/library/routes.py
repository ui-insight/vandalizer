"""Handles file routing."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request, url_for
from flask_login import login_required
from mongoengine.errors import DoesNotExist
from flask_mail import Message

from app import load_user, mail
from app.utilities.security import validate_json_request
from app.models import (  # adjust import path if needed
    Library,
    LibraryItem,
    LibraryScope,
    SearchSet,
    SearchSetItem,
    Team,
    TeamMembership,
    User,
    VerificationRequest,
    VerificationStatus,
    Workflow,
    WorkflowAttachment,
    WorkflowStep,
    WorkflowStepTask,
)
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

    # If there is no library yet, present empty lists gracefully
    lib_items: list[LibraryItem] = list(lib.items) if lib else []

    # Determine which categories we need to collect & cap counts to avoid massive payloads
    needs_workflows = item_type in ("workflows", "all")
    needs_tasks = item_type in ("tasks", "all")
    wants_extract = needs_tasks and (not kinds or "extract" in kinds)
    wants_prompt = needs_tasks and (not kinds or "prompt" in kinds)
    wants_formatter = needs_tasks and (not kinds or "format" in kinds)

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
        if gathered[li.kind] >= limits.get(li.kind, 0):
            # Already have enough of this type
            continue

        identifier = _verification_identifier(li.kind, obj)
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

    # --- Sort (optional niceties)
    workflows.sort(
        key=lambda w: (w.verified is False, (w.updated_at or w.created_at)),
        reverse=True,
    )
    extraction_sets.sort(
        key=lambda s: (s.verified is False, (s.created_at)), reverse=True
    )

    # Assemble context for template
    context = {
        "workflows": workflows,
        "extraction_sets": extraction_sets,
        "prompts": prompts,
        "formatters": formatters,
        "verification_requests": verification_payloads,
        "filters": {
            "type": item_type,
            "kinds": kinds,
            "q": query,
        },
        # expose simple scope used in badges in your _results.html
        "scope": "team"
        if lib_scope == LibraryScope.TEAM
        else ("mine" if lib_scope == LibraryScope.PERSONAL else "verified"),
        "can_edit_verified": can_edit_verified,
    }
    return context


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
    rendered_html = render_template("library/_results.html", **ctx)
    return jsonify({"template": rendered_html})


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


@library.route("/team/remove", methods=["POST"])
def remove_from_team_library():
    user = load_user()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    team = _current_team_for_user(user)
    if not team:
        return jsonify({"error": "no team"}), 400

    membership = TeamMembership.objects(team=team, user_id=user.user_id).first()
    if not membership:
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(force=True) or {}
    uuid = payload.get("uuid")
    kind = payload.get("kind")
    if not uuid or not kind:
        return jsonify({"error": "invalid request"}), 400

    obj, normalized_kind = _resolve_obj(kind, uuid)
    if not obj or not normalized_kind:
        return jsonify({"error": "not found"}), 404

    team_library = Library.objects(
        scope=LibraryScope.TEAM, team=team
    ).first()
    if not team_library:
        return jsonify({"ok": False, "removed": False}), 200

    target_item = None
    for item in list(team_library.items):
        if item.kind == normalized_kind and item.obj == obj:
            target_item = item
            break

    if not target_item:
        return jsonify({"ok": False, "removed": False}), 200

    team_library.items.remove(target_item)
    team_library.updated_at = datetime.now(timezone.utc)
    team_library.save()
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
