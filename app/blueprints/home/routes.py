"""Handles primary routing for the home page and related functionalities."""

import asyncio
import io
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pypandoc
from devtools import debug
from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from markupsafe import escape
from mongoengine.queryset.visitor import Q
from werkzeug.utils import secure_filename

from app import CURRENT_RELEASE_VERSION, RELEASE_NOTES, app, load_user
from app.utilities.security import validate_json_request
from app.models import (
    ActivityEvent,
    ActivityStatus,
    ChatConversation,
    ChatRole,
    FileAttachment,
    SearchSet,
    SearchSetItem,
    SmartDocument,
    SmartFolder,
    Space,
    Team,
    TeamMembership,
    UrlAttachment,
    User,
    UserModelConfig,
    Workflow,
    WorkflowStep,
)
from app.utilities.agents import create_chat_agent
from app.utilities.analytics_helper import (
    ActivityType,
    activity_finish,
    activity_start,
)
from app.utilities.chat_manager import ChatManager
from app.utilities.config import get_default_model_name, settings
from app.utilities.document_manager import (
    cleanup_document,
    perform_extraction_and_update,
    update_document_fields,
)
from app.utilities.document_readers import extract_text_from_file
from app.utilities.library_helpers import (
    _get_or_create_personal_library,
)
from app.utilities.edit_history import history_for
from app.utilities.upload_manager import (
    perform_document_validation,
)
from app.utilities.verification_helpers import user_can_modify_verified
from app.utilities.web_utils import URLContentFetcher  # You already have this

home = Blueprint("home", __name__)

WEBFONTS_DIR = "static/fontawesome/webfonts"

logging.basicConfig(
    format="%(loglevel) | %(filename)s:%(lineno)d | %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)


def verify_document(document: SmartDocument) -> None:
    """Verify and update the document if necessary."""
    debug("Updating old document", document.title)
    debug("Document processing", document.processing)

    extension = document.extension
    print(document.absolute_path)

    if not document.raw_text or document.raw_text == "":
        # Check if the user's model is external
        model_config = UserModelConfig.objects(user_id=document.user_id).first()
        is_external_model = False
        if model_config and model_config.available_models:
            for model in model_config.available_models:
                if model.get("name") == model_config.name:
                    is_external_model = model.get("external", False)
                    break

        extraction_task = perform_extraction_and_update.s(
            document_uuid=document.uuid,
            extension=extension,
        )

        validation_task = perform_document_validation.s(
            document_uuid=document.uuid,
            document_path=str(document.absolute_path),
        )

        if is_external_model:
            # External model: Sequential flow (extraction -> validation)
            # Document not usable until both complete
            workflow = extraction_task | validation_task
            workflow_task_result = workflow.apply_async(
                link=update_document_fields.si(document.uuid),
                link_error=cleanup_document.si(document.uuid),
            )
            document.task_id = workflow_task_result.id
        else:
            # Internal model: Document usable after extraction, validation runs in background
            workflow_task_result = extraction_task.apply_async(
                link=update_document_fields.si(document.uuid),
                link_error=cleanup_document.si(document.uuid),
            )
            document.task_id = workflow_task_result.id

            validation_task_background = perform_document_validation.s(
                document_text=None,
                document_uuid=document.uuid,
                document_path=str(document.absolute_path),
                background=True,
            )
            validation_task_background.apply_async()

        document.processing = True
        document.save()


MAX_BREADCRUMB_DEPTH = 10  # safety to avoid accidental loops


def build_breadcrumbs(
    current_folder_id: str, current_space: str
) -> List[Dict[str, str]]:
    """
    Returns a list of dicts: [{'label': 'Space', 'href': '/?folder_id=0'}, ...]
    - Starts with the space
    - Then each ancestor folder, ending with the current folder
    """

    # Start with Space as the root crumb
    crumbs: List[Dict[str, str]] = [
        {"label": "My Files", "href": url_for("home.index", folder_id="0")}
    ]

    # If we’re at root, we’re done.
    if not current_folder_id or current_folder_id == "0":
        return crumbs

    # Walk up the tree using parent_id
    path: List[Dict[str, str]] = []
    node: Optional[SmartFolder] = SmartFolder.objects(uuid=current_folder_id).first()
    depth = 0

    while node and depth < MAX_BREADCRUMB_DEPTH:
        path.append(
            {"label": node.title, "href": url_for("home.index", folder_id=node.uuid)}
        )
        if not node.parent_id or node.parent_id == "0":
            break
        node = SmartFolder.objects(uuid=node.parent_id).first()
        depth += 1

    # Reverse to go root → … → current
    crumbs.extend(reversed(path))
    return crumbs


@login_required
@home.route("/")
def index() -> ResponseReturnValue:
    """Primary entry point."""
    user = load_user()
    if not user:
        return redirect(url_for("auth.login"))
    section = (request.args.get("section") or "Assistant").strip()

    # Spaces
    spaces_all = _ensure_default_space_and_get_all()
    current_space = _resolve_current_space(spaces_all)
    spaces = _order_spaces_with_current_first(spaces_all, current_space)

    # Documents (may update current_space if a doc lives elsewhere)
    documents, selected_document, maybe_space = _gather_documents()
    if maybe_space is not None:
        current_space = maybe_space
        spaces = _order_spaces_with_current_first(spaces_all, current_space)

    # Workflow templates (string fragments for the page)
    workflow_id = request.args.get("workflow_id", default=0)
    workflow_tpl, workflow_step_tpl = _render_workflow_bits(workflow_id)

    # Query sets & workflows
    extraction_sets, prompts, formatters, workflows = _load_sets_and_workflows(
        user, current_space
    )

    # Folder context
    current_folder_id, current_folder_parent_id, folder_docs, folders, team_folders = (
        _folder_context(user, current_space)
    )

    # Release panel & breadcrumbs
    show_release_panel = request.cookies.get("release_seen") != CURRENT_RELEASE_VERSION
    breadcrumbs = build_breadcrumbs(current_folder_id, current_space)

    # Teams
    current_team, my_teams = _get_teams(user)

    # Activity
    activities_qs = _build_activities(user=user)
    activities = [event_to_dict(a) for a in activities_qs]
    json.dumps(activities)

    # ensure_everyone_has_libraries_and_backfill()

    # Library
    my_library = _get_or_create_personal_library(user_id=user.get_id())
    scope = request.args.get("scope", "mine")  # 'team' | 'mine' | 'verified'
    item_type = request.args.get("type", "all")  # 'workflows' | 'tasks' | 'all'
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = [k for k in kinds_str.split(",") if k] if kinds_str else []
    query = request.args.get("q", "")

    initial_filters = {"scope": scope, "type": item_type, "kinds": kinds, "q": query}

    # Resume activity
    activity_id = request.args.get("activity_id", None)
    activity_type = None

    conversation_uuid = request.args.get("conversation_uuid", None)
    chat_conversation = None
    activity = None
    workflow_result = None
    workflow_activity_snapshot: dict[str, Any] | None = None
    workflow_activity_status: str | None = None
    workflow_activity_id: str | None = None
    extraction_panel_html = None
    if activity_id and len(str(activity_id).strip()) > 0:
        activity = ActivityEvent.objects(id=activity_id).first()
        if activity:
            activity_type = activity.type
            workflow_activity_id = str(activity.id)
            workflow_activity_status = activity.status
            if activity_type == "conversation":
                chat_conversation = ChatConversation.objects(
                    uuid=activity.conversation_id,
                    user_id=user.user_id,
                ).first()
                debug(chat_conversation)
                conversation_uuid = chat_conversation.uuid
            elif activity_type == "workflow_run":
                # Load the workflow result to display
                workflow_result = activity.workflow_result
                if workflow_result and workflow_result.workflow:
                    # Set workflow_id so the workflow panel opens
                    workflow_id = str(workflow_result.workflow.id)
                    workflow_tpl, workflow_step_tpl = _render_workflow_bits(workflow_id)
                    # Ensure the Library section is active beneath the workflow panel
                    section = "Library"
                    debug(
                        f"Loading workflow {workflow_id} from activity, template length: {len(workflow_tpl)}"
                    )
                    snapshot: dict[str, Any] = dict(activity.result_snapshot or {})
                    if workflow_result.final_output and isinstance(
                        workflow_result.final_output, dict
                    ):
                        final_output_value = workflow_result.final_output.get("output")
                        if final_output_value is not None and "output" not in snapshot:
                            snapshot["output"] = final_output_value
                    if (
                        workflow_result.num_steps_total is not None
                        and "steps_total" not in snapshot
                    ):
                        snapshot["steps_total"] = workflow_result.num_steps_total
                    if (
                        workflow_result.num_steps_completed is not None
                        and "steps_completed" not in snapshot
                    ):
                        snapshot["steps_completed"] = (
                            workflow_result.num_steps_completed
                        )
                    if workflow_result.status and "status" not in snapshot:
                        snapshot["status"] = workflow_result.status
                    if workflow_result.session_id and "session_id" not in snapshot:
                        snapshot["session_id"] = workflow_result.session_id
                    if activity.started_at and "started_at" not in snapshot:
                        snapshot["started_at"] = activity.started_at.isoformat()
                    if activity.finished_at and "finished_at" not in snapshot:
                        snapshot["finished_at"] = activity.finished_at.isoformat()
                    if (
                        activity.started_at
                        and activity.finished_at
                        and "duration_seconds" not in snapshot
                    ):
                        snapshot["duration_seconds"] = (
                            activity.finished_at - activity.started_at
                        ).total_seconds()
                    workflow_activity_snapshot = snapshot or None

                    stored_doc_uuids = snapshot.get("document_uuids") or []
                    workflow_documents: list[SmartDocument] = []
                    for doc_uuid in stored_doc_uuids:
                        doc = SmartDocument.objects(uuid=doc_uuid).first()
                        if doc:
                            workflow_documents.append(doc)
                    if workflow_documents:
                        documents = workflow_documents
                        selected_document = workflow_documents[0]
            elif activity_type == "search_set_run":
                # Load the search set to display
                search_set_uuid = activity.search_set_uuid
                if search_set_uuid:
                    search_set = SearchSet.objects(uuid=search_set_uuid).first()
                    if search_set:
                        snapshot = activity.result_snapshot or {}
                        stored_results = snapshot.get("normalized") or snapshot.get(
                            "raw"
                        )
                        stored_doc_uuids = snapshot.get("document_uuids") or []
                        snapshot_documents = []
                        for doc_uuid in stored_doc_uuids:
                            doc = SmartDocument.objects(uuid=doc_uuid).first()
                            if doc:
                                snapshot_documents.append(doc)

                        if snapshot_documents:
                            documents = snapshot_documents
                            selected_document = snapshot_documents[0]

                        # Switch to Library section and show the extraction panel
                        section = "Library"
                        # Render the extraction panel without results (user can re-run if needed)
                        extraction_panel_html = render_template(
                            "toolpanel/extractions/extraction_panel.html",
                            search_set=search_set,
                            documents=snapshot_documents or documents,
                            results=stored_results,
                            history_entries=history_for("searchset", search_set.uuid),
                        )

    debug(activity)
    if chat_conversation:
        chat_conversation = chat_conversation.to_dict()

    if extraction_panel_html is None:
        search_set_uuid_param = request.args.get("search_set_uuid")
        if search_set_uuid_param:
            search_set = SearchSet.objects(uuid=search_set_uuid_param).first()
            if search_set:
                section = "Library"
                extraction_panel_html = render_template(
                    "toolpanel/extractions/extraction_panel.html",
                    search_set=search_set,
                    documents=documents,
                    results=None,
                    history_entries=history_for("searchset", search_set.uuid),
                )

    return render_template(
        "index.html",
        extraction_sets=extraction_sets,
        activity=activity,
        chat_conversation=chat_conversation,
        prompts=prompts,
        formatters=formatters,
        folders=folders,
        team_folders=team_folders,
        current_folder_parent_id=current_folder_parent_id,
        current_folder_id=current_folder_id,
        documents=documents,
        conversation_id=conversation_uuid,
        selected_document=selected_document,
        folder_docs=folder_docs,
        spaces=spaces,
        current_space_id=spaces[0].uuid,
        section=section,
        max_context_length=settings.max_context_length,
        workflows=workflows,
        workflow_template=workflow_tpl,
        workflow_step_template=workflow_step_tpl,
        workflow_id=workflow_id,
        workflow_result=workflow_result,
        extraction_panel_html=extraction_panel_html,
        release_notes=RELEASE_NOTES,
        show_release_panel=show_release_panel,
        current_release=CURRENT_RELEASE_VERSION,
        breadcrumbs=breadcrumbs,
        is_admin=user.is_admin,
        activities=activities,
        current_team=current_team,
        my_teams=my_teams,
        my_library=my_library,
        initial_library_results="",
        filters=initial_filters,
        scope=scope,
        can_verify=user.is_examiner,
        workflow_activity_snapshot=workflow_activity_snapshot,
        workflow_activity_status=workflow_activity_status,
        workflow_activity_id=workflow_activity_id,
    )


# ---------------------------- helpers ----------------------------


def event_to_dict(a: ActivityEvent) -> dict:
    return {
        "id": str(a.id),
        "type": str(a.type),
        "status": str(a.status),
        "title": str(a.title),
        "conversation_id": str(a.conversation_id) if a.conversation_id else None,
        "search_set_uuid": str(a.search_set_uuid) if a.search_set_uuid else None,
        "workflow_id": str(a.workflow.id) if a.workflow else None,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "finished_at": a.finished_at.isoformat() if a.finished_at else None,
        "error": str(a.error) if a.error else "",
        "tokens_input": a.tokens_input,
        "tokens_output": a.tokens_output,
        "message_count": a.message_count,
        "result_snapshot": a.result_snapshot or {},
    }


def _get_teams(user: User) -> tuple[Team, list[TeamMembership]]:
    current_team = user.ensure_current_team()
    my_teams = TeamMembership.objects(user_id=user.get_id())
    return (current_team, my_teams)


def _ensure_default_space_and_get_all() -> list[Space]:
    """Guarantee at least one Space exists; return all spaces."""
    spaces = list(Space.objects())
    if not spaces:
        Space(title="Default Space", uuid=uuid.uuid4().hex).save()
        spaces = list(Space.objects())
    return spaces


def _resolve_current_space(spaces: list[Space]) -> Space:
    """Pick current space from query, session, or first available."""
    q_space_id = request.args.get("space_id")
    if q_space_id:
        session["space_id"] = q_space_id
        found = Space.objects(uuid=q_space_id).first()
        if found:
            return found

    sess_id = session.get("space_id")
    if sess_id:
        found = Space.objects(uuid=sess_id).first()
        if found:
            return found

    return spaces[0]


def _order_spaces_with_current_first(
    spaces_all: list[Space], current: Space
) -> list[Space]:
    """Return spaces with current first (no duplicates)."""
    ordered = [current] + [s for s in spaces_all if s.uuid != current.uuid]
    return ordered


def _gather_documents() -> tuple[
    list[SmartDocument], Optional[SmartDocument], Optional[Space]
]:
    """
    Collect selected docs based on 'docid'/'docids'.
    Returns (documents, selected_document, current_space_override_if_any).
    """
    documents: list[SmartDocument] = []
    selected_document: Optional[SmartDocument] = None
    space_override: Optional[Space] = None

    doc_id = request.args.get("docid")
    if doc_id:
        d = SmartDocument.objects(uuid=doc_id).first()
        if d:
            documents.append(d)
            verify_document(d)
            selected_document = d
            space_override = Space.objects(uuid=d.space).first()

    doc_ids = request.args.get("docids")
    if doc_ids:
        for did in doc_ids.split(","):
            d = SmartDocument.objects(uuid=did).first()
            if d:
                documents.append(d)
                verify_document(d)
                # keep last space encountered (prior behavior used the last doc)
                space_override = Space.objects(uuid=d.space).first()

    return documents, selected_document, space_override


def _render_workflow_bits(workflow_id: Any) -> tuple[str, str]:
    """Render workflow and (optional) workflow-step templates."""
    if not workflow_id or workflow_id == 0:
        return "", ""

    # Use the passed workflow_id parameter, or fall back to request.args
    wf_id = (
        workflow_id
        if workflow_id and workflow_id != 0
        else request.args.get("workflow_id")
    )
    workflow = Workflow.objects(id=wf_id).first()
    if not workflow:
        return "", ""

    can_customize = user_can_modify_verified(load_user(), workflow)

    # Prepare workflow configuration for JS (Input/Output tabs)
    user = load_user()
    workflow_config = {}
    
    if user:
        # Get available folders for the user
        folders = SmartFolder.objects(user_id=user.get_id()).only('uuid', 'title', 'parent_id')
        
        # Build folder paths
        available_folders = []
        for folder in folders:
            # Build folder path by traversing parents
            path_parts = [folder.title]
            current = folder
            while current.parent_id and current.parent_id != "0":
                parent = SmartFolder.objects(uuid=current.parent_id).only('title', 'parent_id').first()
                if parent:
                    path_parts.insert(0, parent.title)
                    current = parent
                else:
                    break
            
            available_folders.append({
                'uuid': folder.uuid,
                'title': folder.title,
                'path': ' / '.join(path_parts)
            })

        workflow_config = {
            'workflow_id': str(workflow.id),
            'input_config': workflow.input_config or {},
            'output_config': workflow.output_config or {},
            'available_folders': available_folders
        }

    workflow_tpl = render_template(
        "workflows/workflow.html",
        workflow=workflow,
        can_customize_workflow=can_customize,
        workflow_config=workflow_config,
    )

    step_tpl = ""
    step_id = request.args.get("workflow_step_id", default=0)
    if step_id and step_id != 0:
        workflow_step = WorkflowStep.objects(id=step_id).first()
        if workflow_step:
            step_tpl = render_template(
                "workflows/workflow_steps/edit_workflow_step_modal.html",
                workflow=workflow,
                workflow_step_id=workflow_step.id,
                workflow_step=workflow_step,
            )
    return workflow_tpl, step_tpl


def _load_sets_and_workflows(user, current_space: Space):
    """Load extraction sets, prompt/formatter items, and user workflows."""
    global_extraction_sets = SearchSet.objects(
        space=current_space.uuid, is_global=True, set_type="extraction"
    ).all()
    user_extraction_sets = SearchSet.objects(
        user_id=user.get_id(),
        space=current_space.uuid,
        is_global=False,
        set_type="extraction",
    ).all()
    extraction_sets = list(chain(global_extraction_sets, user_extraction_sets))

    prompts = SearchSetItem.objects(
        user_id=user.get_id(), space_id=current_space.uuid, searchtype="prompt"
    ).all()

    formatters = SearchSetItem.objects(
        user_id=user.get_id(), space_id=current_space.uuid, searchtype="formatter"
    ).all()

    workflows = Workflow.objects(user_id=user.get_id()).all()

    return extraction_sets, prompts, formatters, workflows


def _folder_context(user, current_space: Space):
    """
    Resolve folder id/parent, gather docs & subfolders.
    Returns (current_folder_id, current_folder_parent_id, folder_docs, folders).
    """
    current_folder_id = request.args.get("folder_id", default="0")
    current_folder_parent_id = "0"

    # Check if current folder is a team folder
    is_team_folder = False
    if current_folder_id not in {"0", 0}:
        folder = SmartFolder.objects(uuid=current_folder_id).first()
        if folder:
            current_folder_parent_id = folder.parent_id
            # If the folder has a team_id, it's a team folder
            is_team_folder = bool(folder.team_id)

    # Build document query - if it's a team folder, show all docs in that folder
    # Otherwise, show only user's docs
    if is_team_folder:
        base_query = Q(space=current_space.uuid, folder=current_folder_id)
    else:
        base_query = Q(
            user_id=user.get_id(), space=current_space.uuid, folder=current_folder_id
        )

    default_doc_query = Q(user_id=user.get_id(), is_default=True)
    folder_docs = (
        SmartDocument.objects(base_query | default_doc_query)
        .order_by("-created_at")
        .all()
    )

    parent_filter = current_folder_id if current_folder_id not in {"0", 0} else "0"

    folders = SmartFolder.objects(
        user_id=user.get_id(),
        space=current_space.uuid,
        parent_id=parent_filter,
    ).all()

    current_team = user.ensure_current_team()
    if current_team:
        current_team.ensure_shared_folder(space_id=current_space.uuid)
        team_folders = (
            SmartFolder.objects(
                team_id=current_team.uuid,
                parent_id=parent_filter,
            )
            .order_by("-is_shared_team_root", "title")
            .all()
        )
    else:
        team_folders = []

    return (
        current_folder_id,
        current_folder_parent_id,
        folder_docs,
        folders,
        team_folders,
    )


def _build_activities(user: User) -> list[ActivityEvent]:
    """Get the last 20 activities for the user, including completed ones."""
    # Get last 20 activities, ordered by most recent
    activities = list(
        ActivityEvent.objects(user_id=user.get_id())
        .order_by("-last_updated_at", "-id")
        .limit(20)
    )

    visible_activities: list[ActivityEvent] = []
    for activity in activities:
        # Keep workflow activities in sync with their workflow result status
        if (
            activity.type == ActivityType.WORKFLOW_RUN.value
            and activity.workflow_result is not None
        ):
            result_status = (activity.workflow_result.status or "").lower()
            if result_status in {
                ActivityStatus.COMPLETED.value,
                ActivityStatus.FAILED.value,
                ActivityStatus.CANCELED.value,
            }:
                if activity.status != result_status:
                    status_enum = ActivityStatus(result_status)
                    activity_finish(activity, status=status_enum)
                    activity.reload()

        visible_activities.append(activity)

    return visible_activities


@home.route("/chat", methods=["POST"])
@login_required
@validate_json_request()
def chat() -> ResponseReturnValue:
    """Handle chat requests."""
    data = request.get_json()
    raw_message = data["message"]
    message = raw_message
    activity_id = data.get("activity_id", None)
    current_space_id = data.get("current_space_id", None)
    # get activity if it exists
    debug("Message received:", message)
    message = escape(message)
    debug("Sanitized message:", message)
    # sanitize message

    document_uuids = data["document_uuids"]
    folder = data["folder_uuid"]
    documents = []
    user = current_user
    user_id = user.get_id()

    current_team, my_teams = _get_teams(user)
    debug(current_team)
    debug(my_teams)

    activity = None
    conversation = None
    title = message.strip()
    if not activity_id or len(str(activity_id).strip()) < 10:
        conversation = ChatConversation(
            title=title,
            uuid=str(uuid.uuid4()),
            user_id=user_id,
        )
        conversation.save()
        conversation.generate_title()
        activity = activity_start(
            type=ActivityType.CONVERSATION,
            title=None,  # Will be auto-generated from document content
            user_id=user_id,
            team_id=user.ensure_current_team().uuid,
            conversation_id=conversation.uuid,
            space=current_space_id,
            document_uuids=document_uuids,
        )
        # If this chat isn't tied to any documents, we won't run the LLM-based
        # activity description job. In that case, set a simple safe title
        # immediately so the app rail doesn't stay stuck on "Generating title…".
        if (not document_uuids) and (not activity.title):
            first_line = (raw_message or "").strip().splitlines()[0] if raw_message else ""
            words = [w for w in first_line.split() if w]
            short = " ".join(words[:8]).strip()
            if not short:
                short = "Chat"
            if len(short) > 80:
                short = short[:77].rstrip() + "..."
            activity.title = escape(short)
            activity.save()

    else:
        activity = ActivityEvent.objects(id=activity_id).first()
        if activity:
            activity.status = ActivityStatus.RUNNING
            activity.last_updated_at = datetime.now(timezone.utc)
            activity.save()
            conversation = ChatConversation.objects(
                uuid=activity.conversation_id,
                user_id=user_id,
            ).first()
            # If conversation doesn't exist, create a new one and update the activity
            if not conversation:
                conversation = ChatConversation(
                    title=title,
                    uuid=str(uuid.uuid4()),
                    user_id=user_id,
                )
                conversation.save()
                conversation.generate_title()
                activity.conversation_id = conversation.uuid
                activity.save()

    # Ensure conversation exists before proceeding
    if not conversation:
        return jsonify({"error": "Failed to create or retrieve conversation"}), 500

    debug(activity)
    debug(conversation)
    conversation.add_message(ChatRole.USER, message)

    # migrate to new document user's location
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid, is_default=False).first()
        if document is not None:
            documents.append(document)

    debug("Documents", [document.extension for document in documents])
    # default context docs
    docs = SmartDocument.objects(folder=folder, is_default=True).all()

    model_config = UserModelConfig.objects(user_id=user_id).first()
    if model_config:
        model = model_config.name
    else:
        model = get_default_model_name()

    def generate():
        for chunk in ChatManager().ask_question_to_documents_stream(
            model,
            current_app.root_path,
            documents,
            message,
            previous_messages=conversation.to_model_messages(),
            conversation_uuid=conversation.uuid,
            default_docs=docs,
            user_id=user_id,
            session=session,
        ):
            # You can yield raw text, HTML, JSON, or Server-Sent Events.
            yield chunk

    # Use the appropriate MIME type. If you use Server-Sent Events, it's "text/event-stream".
    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["X-Conversation-UUID"] = conversation.uuid
    if activity:
        resp.headers["X-Activity-ID"] = str(activity.id)
    return resp


@home.route("/chat/add_link", methods=["POST"])
def add_link_to_chat():
    """Add a URL attachment to a chat conversation."""
    try:
        data = request.get_json()
        link = data.get("link")
        current_space_id = data.get("current_space_id", None)
        current_activity_id = data.get("current_activity_id", None)

        user = load_user()
        user_id = user.get_id()

        # Validate URL
        # if not link or not link.startswith(('http://', 'https://')):
        #     return jsonify({"error": "Invalid URL"}), 400

        # Get or create conversation

        if not current_activity_id or len(str(current_activity_id).strip()) == 0:
            conversation = ChatConversation(
                user_id=user_id, uuid=str(uuid.uuid4()), title="Link Attached"
            )
            conversation.save()
            activity = activity_start(
                title="Link Attached",
                type=ActivityType.CONVERSATION,
                user_id=user_id,
                team_id=user.ensure_current_team().uuid,
                conversation_id=conversation.uuid,
                space=current_space_id,
            )

        else:
            activity = ActivityEvent.objects(id=current_activity_id).first()
            if activity:
                activity.status = ActivityStatus.RUNNING
                activity.last_updated_at = datetime.now(timezone.utc)
                activity.save()
                conversation = ChatConversation.objects(
                    uuid=activity.conversation_id,
                    user_id=user_id,
                ).first()

        session["current_activity_id"] = str(activity.id)
        session["current_conversation_id"] = str(conversation.id)

        debug(link)
        debug(conversation)

        # Fetch URL content
        fetcher = URLContentFetcher(max_content_length=500000)
        result = fetcher.fetch_url_content(link)

        # Check if the fetch failed
        if result is None:
            # Mark activity as failed before returning error
            if activity:
                activity_finish(
                    activity,
                    status=ActivityStatus.FAILED,
                    error="Invalid URL or unsupported content type",
                )
            return jsonify(
                {
                    "error": "Invalid URL or unsupported content type",
                    "activity_id": str(activity.id) if activity else None,
                }
            ), 400

        if result.get("error"):
            # Mark activity as failed before returning error
            if activity:
                activity_finish(
                    activity,
                    status=ActivityStatus.FAILED,
                    error=f"Failed to fetch URL: {result.get('error')}",
                )
            return jsonify(
                {
                    "error": f"Failed to fetch URL: {result.get('error')}",
                    "activity_id": str(activity.id) if activity else None,
                }
            ), 400

        # Extract title from URL or content
        title = urlparse(link).netloc
        title = result.get("title", title)
        content = result.get("content", "")

        debug(content)
        debug(title)

        # Create URL attachment
        url_attachment = UrlAttachment(
            url=link, title=title, content=content, user_id=user_id
        )
        url_attachment.save()

        # Add to conversation
        conversation.url_attachments.append(url_attachment)
        conversation.updated_at = datetime.now()

        # add url attachment message to chat
        conversation.add_message(
            ChatRole.USER, f"[Link attached: {title}]\nURL: {link}]"
        )

        conversation.save()
        conversation.reload()

        # Don't mark as completed - keep the conversation active so user can continue chatting
        # The activity will remain visible in the rail

        return jsonify(
            {
                "success": True,
                "conversation_uuid": conversation.uuid,
                "attachment_id": str(url_attachment.id),
                "title": title,
                "content_preview": content[:500] if content else "",
                "activity_id": str(activity.id) if activity else None,
                "attachment": url_attachment.to_dict(),
            }
        ), 200

    except Exception as e:
        logger.error(f"Error adding URL attachment: {e}")
        # Mark activity as failed on exception
        if "activity" in locals() and activity:
            activity_finish(activity, status=ActivityStatus.FAILED, error=str(e))
        return jsonify(
            {
                "error": str(e),
                "activity_id": str(activity.id)
                if "activity" in locals() and activity
                else None,
            }
        ), 500


@app.route("/chat/add_document", methods=["POST"])
def add_document_to_chat():
    """Add file attachments to a chat conversation."""
    try:
        current_space_id = request.form.get("current_space_id", None)
        current_activity_id = request.form.get("current_activity_id", None)
        debug(request.form)
        user = load_user()
        user_id = user.get_id()

        conversation = None
        activity = None
        if not current_activity_id or len(str(current_activity_id).strip()) < 10:
            conversation = ChatConversation(
                title="Attachments Added",
                uuid=str(uuid.uuid4()),
                user_id=user_id,
            )
            activity = activity_start(
                type=ActivityType.CONVERSATION,
                title="Document Attached",
                user_id=user_id,
                team_id=user.ensure_current_team().uuid,
                conversation_id=conversation.uuid,
                space=current_space_id,
            )
        else:
            activity = ActivityEvent.objects(id=current_activity_id).first()
            if activity:
                activity.status = ActivityStatus.RUNNING
                activity.last_updated_at = datetime.now(timezone.utc)
                activity.save()
                conversation = ChatConversation.objects(
                    uuid=activity.conversation_id,
                    user_id=user_id,
                ).first()

        session["current_activity_id"] = str(activity.id)
        session["current_conversation_id"] = str(conversation.id)

        # Check if files were uploaded
        if "files" not in request.files:
            if activity:
                activity_finish(
                    activity, status=ActivityStatus.FAILED, error="No files uploaded"
                )
            return jsonify(
                {
                    "error": "No files uploaded",
                    "activity_id": str(activity.id) if activity else None,
                }
            ), 400

        files = request.files.getlist("files")
        if not files or files[0].filename == "":
            if activity:
                activity_finish(
                    activity, status=ActivityStatus.FAILED, error="No files selected"
                )
            return jsonify(
                {
                    "error": "No files selected",
                    "activity_id": str(activity.id) if activity else None,
                }
            ), 400

        uploaded_attachments = []

        # Process each uploaded file
        for file in files:
            if file and file.filename:
                # Secure the filename
                filename = secure_filename(file.filename)
                file_extension = os.path.splitext(filename)[1].lower()

                # Create a temporary file
                temp_file = None
                try:
                    # Save to temporary file for processing
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=file_extension, mode="wb"
                    ) as temp_file:
                        file.save(temp_file.name)
                        temp_file_path = temp_file.name

                    debug(f"Processing file: {filename} at {temp_file_path}")

                    # Extract text content using existing logic
                    content = extract_text_from_file(temp_file_path, file_extension)
                    debug(content)

                    # Truncate content if too long (adjust max length as needed)
                    max_content_length = 50000
                    if len(content) > max_content_length:
                        content = (
                            content[:max_content_length] + "\n\n[Content truncated...]"
                        )

                    debug(f"Extracted {len(content)} characters from {filename}")

                    # Create file attachment record
                    file_attachment = FileAttachment(
                        filename=filename,
                        content=content,
                        file_type=file_extension,
                        user_id=user_id,
                    )
                    file_attachment.save()

                    # Add to conversation
                    conversation.file_attachments.append(file_attachment)
                    # add file attachment message to chat
                    conversation.add_message(
                        ChatRole.USER,
                        f"📎 File attached: {filename} ({len(content):,} characters)",
                    )

                    uploaded_attachments.append(
                        {
                            "id": str(file_attachment.id),
                            "filename": filename,
                            "file_type": file_extension,
                            "content_preview": content[:500] if content else "",
                            "content_length": len(content),
                            "created_at": file_attachment.created_at.isoformat(),
                        }
                    )

                except Exception as e:
                    logger.error(f"Error processing file {filename}: {e}")
                    debug(f"Error processing file {filename}: {e}")
                    # Still create an attachment with error message
                    file_attachment = FileAttachment(
                        filename=filename,
                        content=f"[Error processing file: {str(e)}]",
                        file_type=file_extension,
                        user_id=user_id,
                    )
                    file_attachment.save()
                    conversation.file_attachments.append(file_attachment)

                    uploaded_attachments.append(
                        {
                            "id": str(file_attachment.id),
                            "filename": filename,
                            "file_type": file_extension,
                            "content_preview": f"Error: {str(e)}",
                            "content_length": 0,
                            "created_at": file_attachment.created_at.isoformat(),
                        }
                    )

                finally:
                    # Clean up temporary file
                    if temp_file and os.path.exists(temp_file_path):
                        try:
                            os.unlink(temp_file_path)
                            debug(f"Cleaned up temp file: {temp_file_path}")
                        except Exception as e:
                            logger.error(f"Error deleting temp file: {e}")

        # Update conversation timestamp
        conversation.updated_at = datetime.now()
        conversation.save()
        conversation.reload()

        # Don't mark as completed - keep the conversation active so user can continue chatting
        # The activity will remain visible in the rail

        return jsonify(
            {
                "success": True,
                "conversation_uuid": conversation.uuid,
                "attachments": uploaded_attachments,
                "attachment": uploaded_attachments[0] if uploaded_attachments else None,
                "activity_id": str(activity.id) if activity else None,
            }
        ), 200

    except Exception as e:
        logger.error(f"Error adding file attachments: {e}")
        # Mark activity as failed on exception
        if "activity" in locals() and activity:
            activity_finish(activity, status=ActivityStatus.FAILED, error=str(e))
        return jsonify(
            {
                "error": str(e),
                "activity_id": str(activity.id)
                if "activity" in locals() and activity
                else None,
            }
        ), 500


@app.route("/chat/remove_document/<attachment_id>", methods=["DELETE"])
def remove_document_from_chat(attachment_id):
    """Remove a file attachment from chat conversation."""
    try:
        user = load_user()
        user_id = user.get_id()

        # Find the attachment
        attachment = FileAttachment.objects(id=attachment_id, user_id=user_id).first()

        if not attachment:
            return jsonify({"error": "Attachment not found"}), 404

        # Find conversation containing this attachment
        conversation = ChatConversation.objects(
            file_attachments=attachment.id, user_id=user_id
        ).first()

        if conversation:
            # Remove from conversation
            conversation.file_attachments = [
                att
                for att in conversation.file_attachments
                if str(att.id) != attachment_id
            ]
            conversation.save()

        # Delete attachment record (no file to delete from disk)
        attachment.delete()

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error removing file attachment: {e}")
        return jsonify({"error": str(e)}), 500


@home.route("/chat_history/<conversation_uuid>", methods=["GET"])
def get_chat_history(conversation_uuid):
    """Get chat conversation history."""
    try:
        user = load_user()
        user_id = user.get_id()
        conversation = ChatConversation.objects(
            uuid=conversation_uuid, user_id=user_id
        ).first()

        if not conversation:
            return jsonify({"messages": [], "url_attachments": []}), 404

        # Include URL attachments if they exist
        url_attachments = []
        for attachment in conversation.url_attachments:
            url_attachments.append(
                {
                    "url": attachment.url,
                    "title": attachment.title,
                    "created_at": attachment.created_at.isoformat(),
                }
            )

        return jsonify(
            {
                "messages": conversation.get_messages(),
                "url_attachments": url_attachments,
            }
        )
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return jsonify({"error": "Failed to fetch conversation"}), 500


@home.route("/chat_history/<conversation_uuid>", methods=["DELETE"])
def delete_chat_history(conversation_uuid):
    """Delete a chat conversation."""
    try:
        # Get the current user
        user = load_user()
        user_id = user.get_id()

        # Find the conversation and verify it belongs to the user
        conversation = ChatConversation.objects(
            uuid=conversation_uuid, user_id=user_id
        ).first()

        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        # Delete associated attachments first (if not cascade deleting)
        # This depends on your model setup - if CASCADE is set, this happens automatically
        for attachment in conversation.file_attachments:
            attachment.delete()

        for attachment in conversation.url_attachments:
            attachment.delete()

        # Delete all messages (they should cascade delete due to your model setup)
        # But explicitly delete them to be safe
        for message in conversation.messages:
            message.delete()

        # Delete the conversation itself
        conversation.delete()

        return jsonify(
            {"success": True, "message": "Conversation deleted successfully"}
        ), 200

    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return jsonify({"error": f"Failed to delete conversation: {str(e)}"}), 500


## @MARK: Download
@home.route("/chat/download", methods=["POST"])
def chat_download() -> ResponseReturnValue:
    fmt = request.args.get("format", "txt").lower()

    if request.is_json:
        final_output = request.json.get("content", "")
    else:
        final_output = request.form.get("content", "")

    #    tailor the prompt to each format
    if fmt == "csv":
        prompt = (
            "Convert the following HTML document into a well formatted CSV. "
            "Use commas as separators and include a header row.\n\n"
            "Do not include any description of your own or commentary, just return what we are going to output.\n\n"
            f"{final_output}"
        )
    elif fmt == "pdf":
        # you might ask for a simple text layout or markdown-to-PDF
        prompt = (
            "Lay out the following HTML data into a well-structured document that I can export as a PDF. "
            "Please format your entire response using gorgeous modern designed html.\n\n"
            "Use headings, paragraphs, bullet points, and bold text as appropriate to create a clear and readable layout. "
            "Do not include any of your own commentary or descriptions outside of the Markdown output.\n\n"
            f"Here is the HTML data:\n\n{final_output}"
        )
    else:  # txt
        prompt = (
            "Pretty-print the following HTML document into a well-formatted text document. Strip out all html tags. Just give me clean, indented text.\n\n"
            "Do not include any description of your own or commentary, just return what we are going to output.\n\n"
            f"{final_output}"
        )

    user = load_user()
    user_id = user.get_id()
    model_config = UserModelConfig.objects(user_id=user_id).first()
    if model_config:
        model = model_config.name
    else:
        model = get_default_model_name()

    if fmt == "pdf":
        formatted = final_output
    else:
        chat_agent = create_chat_agent(model)
        # get current event loop
        # if there is no current loop, create a new one
        formatted = asyncio.run(chat_agent.run(prompt))
        formatted = formatted.output

        # Remove the tick marks before and after blocks
        formatted = formatted.strip("`").strip()

    # 4) package it up
    buf = io.BytesIO()
    debug(f"Format is {fmt}")
    if fmt == "csv":
        buf.write(formatted.encode("utf-8"))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name="chat_output.csv",
        )

    elif fmt == "pdf":
        buf = markdown_or_html_to_pdf_bytes(formatted, input_format="html")
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="chat_output.pdf",
        )

    else:  # txt
        buf.write(formatted.encode("utf-8"))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/plain",
            as_attachment=True,
            download_name="chat_output.txt",
        )


def markdown_or_html_to_pdf_bytes(
    input_text: str,
    input_format: str = "markdown",  # or "html"
    extra_args: list[str] | None = None,
) -> io.BytesIO:
    """
    Convert Markdown or HTML to PDF bytes using pandoc (via pypandoc).
    Requires pandoc installed; for high-quality output you typically want a LaTeX engine (xelatex).
    """
    if extra_args is None:
        extra_args = [
            "--pdf-engine=xelatex",
        ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "export.pdf"
        # Pandoc writes binary PDFs only when outputfile is specified
        pypandoc.convert_text(
            input_text,
            to="pdf",
            format=input_format,
            outputfile=str(out_path),
            extra_args=extra_args,
        )
        bio = io.BytesIO(out_path.read_bytes())
        bio.seek(0)
        return bio


@home.route("/static/fontawesome/webfonts/<path:filename>")
def serve_fonts(filename):
    if filename.endswith(".woff2"):
        return send_from_directory(
            WEBFONTS_DIR,
            filename,
            mimetype="font/woff2",
        )
    if filename.endswith(".ttf"):
        return send_from_directory(
            WEBFONTS_DIR,
            filename,
            mimetype="font/ttf",
        )
    return send_from_directory(WEBFONTS_DIR, filename)
