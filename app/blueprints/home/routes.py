"""Handles primary routing for the home page and related functionalities."""

import asyncio
import io
import json
import logging
import uuid
from datetime import datetime
from itertools import chain
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from devtools import debug
from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
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

from app import CURRENT_RELEASE_VERSION, RELEASE_NOTES, app
from app.blueprints.library.routes import _build_results_for_template
from app.models import (
    ActivityEvent,
    ChatConversation,
    ChatRole,
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
    activity_start,
    recent_activity_for_feed,
)
from app.utilities.chat_manager import ChatManager
from app.utilities.config import settings
from app.utilities.document_manager import (
    cleanup_document,
    perform_extraction_and_update,
    update_document_fields,
)
from app.utilities.library_helpers import (
    _get_or_create_personal_library,
)
from app.utilities.markdown_helpers import (
    generate_pdf_from_html,
)
from app.utilities.upload_manager import (
    perform_document_validation,
)
from app.utilities.web_utils import URLContentFetcher  # You already have this
from app.utils import load_user

home = Blueprint("home", __name__)

WEBFONTS_DIR = "static/fontawesome/webfonts"

logger = logging.getLogger(__name__)


@login_required
@app.context_processor
def inject_current_model():
    """
    Runs on *every* template render.  Looks up the user's ModelConfig,
    and makes `current_model` available in all templates.
    """
    # user = current_user
    # if user:
    #     model_config = UserModelConfig.objects(user_id=user.user_id).first()
    #     models = [m.model_dump() for m in settings.models]
    #     current_model = settings.base_model
    #     if model_config:
    #         current_model = model_config.name
    #         if len(model_config.available_models) > 0:
    #             models = json.loads(json.dumps(model_config.available_models))

    #     return {"current_model": current_model, "models": models}

    return {"current_model": "", "models": []}


def verify_document(document: SmartDocument) -> None:
    """Verify and update the document if necessary."""
    debug("Updating old document", document.title)
    debug("Document processing", document.processing)

    extension = document.extension

    if not document.raw_text or document.raw_text == "":
        extraction_task = perform_extraction_and_update.s(
            document_uuid=document.uuid,
            extension=extension,
        )

        validation_task = perform_document_validation.s(
            document_uuid=document.uuid,
            document_path=str(document.absolute_path),
        )

        workflow = extraction_task | validation_task  # | ingestion_task
        workflow_task_result = workflow.apply_async(
            link=update_document_fields.si(document.uuid),
            link_error=cleanup_document.si(document.uuid),
        )
        document.task_id = workflow_task_result.id
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
    if user is None:
        return
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

    conversations = (
        ChatConversation.objects(user_id=user.user_id).order_by("-created_at").all()
    )

    # Teams
    current_team, my_teams = _get_teams(user)

    # Activity
    activities_qs = _build_activities(user=user)
    activities = [event_to_dict(a) for a in activities_qs]

    json.dumps(activities)
    print(activities)

    # ensure_everyone_has_libraries_and_backfill()

    # Library
    my_library = _get_or_create_personal_library(user_id=user.user_id)
    scope = request.args.get("scope", "team")  # 'team' | 'mine' | 'verified'
    item_type = request.args.get("type", "workflows")  # 'workflows' | 'tasks' | 'all'
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = [k for k in kinds_str.split(",") if k] if kinds_str else []
    query = request.args.get("q", "")

    initial_filters = {"scope": scope, "type": item_type, "kinds": kinds, "q": query}
    initial_library_results = _initial_library_results(request)

    return render_template(
        "index.html",
        extraction_sets=extraction_sets,
        prompts=prompts,
        formatters=formatters,
        folders=folders,
        team_folders=team_folders,
        current_folder_parent_id=current_folder_parent_id,
        current_folder_id=current_folder_id,
        documents=documents,
        conversations=conversations,
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
        release_notes=RELEASE_NOTES,
        show_release_panel=show_release_panel,
        current_release=CURRENT_RELEASE_VERSION,
        breadcrumbs=breadcrumbs,
        is_admin=user.is_admin,
        activities=activities,
        current_team=current_team,
        my_teams=my_teams,
        my_library=my_library,
        initial_library_results=initial_library_results,
        filters=initial_filters,
    )


# ---------------------------- helpers ----------------------------


def event_to_dict(a: ActivityEvent) -> dict:
    return {
        "id": str(a.id),
        "type": str(a.type),
        "status": str(a.status),
        "title": str(a.meta_summary.get("title") or "Activity"),
        "conversation_id": str(a.conversation_id) if a.conversation_id else None,
        "search_set_uuid": str(a.search_set_uuid) if a.search_set_uuid else None,
        "workflow_id": str(a.workflow.id) if a.workflow else None,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "finished_at": a.finished_at.isoformat() if a.finished_at else None,
        "error": str(a.error) if a.error else "",
    }


def _initial_library_results(request: Any) -> str:
    scope = request.args.get("scope", "mine")  # 'team' | 'mine' | 'verified'
    item_type = request.args.get("type", "all")  # 'workflows' | 'tasks' | 'all'
    kinds_str = request.args.get("kinds", "extract,prompt,format")
    kinds = [k for k in kinds_str.split(",") if k] if kinds_str else []
    query = request.args.get("q", "")

    initial_filters = {"scope": scope, "type": item_type, "kinds": kinds, "q": query}
    ctx = _build_results_for_template(initial_filters)

    # Render the partial once for first load so the panel is filled immediately
    return render_template("library/_results.html", **ctx)


def _get_teams(user: User) -> tuple[Team, list[TeamMembership]]:
    current_team = user.ensure_current_team()
    my_teams = TeamMembership.objects(user_id=user.user_id)
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

    workflow = Workflow.objects(id=request.args.get("workflow_id")).first()
    if not workflow:
        return "", ""

    workflow_tpl = render_template("workflows/workflow.html", workflow=workflow)

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
        user_id=user.user_id,
        space=current_space.uuid,
        is_global=False,
        set_type="extraction",
    ).all()
    extraction_sets = list(chain(global_extraction_sets, user_extraction_sets))

    prompts = SearchSetItem.objects(
        user_id=user.user_id, space_id=current_space.uuid, searchtype="prompt"
    ).all()

    formatters = SearchSetItem.objects(
        user_id=user.user_id, space_id=current_space.uuid, searchtype="formatter"
    ).all()

    workflows = Workflow.objects(user_id=user.user_id).all()

    return extraction_sets, prompts, formatters, workflows


def _folder_context(user, current_space: Space):
    """
    Resolve folder id/parent, gather docs & subfolders.
    Returns (current_folder_id, current_folder_parent_id, folder_docs, folders).
    """
    current_folder_id = request.args.get("folder_id", default="0")
    current_folder_parent_id = "0"

    base_query = Q(
        user_id=user.user_id, space=current_space.uuid, folder=current_folder_id
    )
    default_doc_query = Q(user_id=user.user_id, is_default=True)
    folder_docs = (
        SmartDocument.objects(base_query | default_doc_query)
        .order_by("-created_at")
        .all()
    )

    if current_folder_id not in {"0", 0}:
        folder = SmartFolder.objects(uuid=current_folder_id).first()
        if folder:
            current_folder_parent_id = folder.parent_id

    folders = SmartFolder.objects(
        team_id=user.user_id,
        space=current_space.uuid,
        parent_id=current_folder_id if current_folder_id != 0 else "0",
    ).all()

    current_team = user.ensure_current_team()
    team_folders = SmartFolder.objects(
        team_id=current_team.uuid,
        parent_id=current_folder_id if current_folder_id != 0 else "0",
    ).all()

    return (
        current_folder_id,
        current_folder_parent_id,
        folder_docs,
        folders,
        team_folders,
    )


def _build_activities(user: User) -> list[ActivityEvent]:
    activities = recent_activity_for_feed(user_id=user.user_id)
    return activities


@home.route("/chat", methods=["POST"])
def chat() -> ResponseReturnValue:
    """Handle chat requests."""
    data = request.get_json()
    message = data["message"]
    conversation_uuid = data.get("conversation_uuid", None)
    debug("Message received:", message)
    debug("Conversation UUID:", conversation_uuid)
    message = escape(message)
    debug("Sanitized message:", message)
    # sanitize message

    document_uuids = data["document_uuids"]
    folder = data["folder_uuid"]
    documents = []
    user = current_user
    user_id = user.user_id

    conversation = ChatConversation.objects(
        uuid=conversation_uuid, user_id=user_id
    ).first()
    if conversation is None:
        title = message.strip()
        conversation = ChatConversation(
            user_id=user.user_id, title=title, uuid=str(uuid.uuid4())
        )
        conversation.generate_title()
        conversation.save()

        conversation.add_message(ChatRole.USER, message)

        current_team, my_teams = _get_teams(user)
        activity_start(
            type=ActivityType.WORKFLOW_RUN,
            user_id=user_id,
            team_id=current_team.uuid,
            conversation_id=conversation.uuid,
        )

    else:
        conversation.add_message(ChatRole.USER, message)

    # migrate to new document user's location
    for doc_uuid in document_uuids:
        document = SmartDocument.objects(uuid=doc_uuid, is_default=False).first()
        if document is not None:
            documents.append(document)

    debug("Documents", [document.extension for document in documents])
    # default context docs
    docs = SmartDocument.objects(folder=folder, is_default=True).all()

    debug(documents)
    debug(docs)
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    if model_config:
        model = model_config.name
    else:
        model = settings.base_model
    print(f"The model is {model}")

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
    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/chat/add_link", methods=["POST"])
def add_link_to_chat():
    """Add a URL attachment to a chat conversation."""
    try:
        data = request.get_json()
        link = data.get("link")
        conversation_uuid = data.get("conversation_uuid")

        user = load_user()
        user_id = user.user_id

        # Validate URL
        # if not link or not link.startswith(('http://', 'https://')):
        #     return jsonify({"error": "Invalid URL"}), 400

        # Get or create conversation
        if conversation_uuid:
            conversation = ChatConversation.objects(
                uuid=conversation_uuid, user_id=user_id
            ).first()
        else:
            # Create new conversation if none exists
            conversation = ChatConversation(
                uuid=str(uuid.uuid4()), user_id=user_id, title="New Conversation"
            )
            conversation.save()

        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        debug(link)
        debug(conversation)

        # Fetch URL content
        fetcher = URLContentFetcher(max_content_length=50000)
        result = fetcher.fetch_url_content(link)

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
        conversation.save()

        return jsonify(
            {
                "success": True,
                "conversation_uuid": conversation.uuid,
                "attachment_id": str(url_attachment.id),
                "title": title,
                "content_preview": content[:500] if content else "",
            }
        ), 200

    except Exception as e:
        logger.error(f"Error adding URL attachment: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/chat_history/<conversation_uuid>", methods=["GET"])
def get_chat_history(conversation_uuid):
    """Get chat conversation history."""
    try:
        user = load_user()
        conversation = ChatConversation.objects(
            uuid=conversation_uuid, user_id=user.user_id
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


@app.route("/chat_history/<conversation_uuid>", methods=["DELETE"])
def delete_chat_history(conversation_uuid):
    """Delete a chat conversation."""
    try:
        # Get the current user
        user = load_user()
        user_id = user.user_id

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

    user = current_user
    model_config = UserModelConfig.objects(user_id=user.user_id).first()
    if model_config:
        model = model_config.name
    else:
        model = settings.base_model
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
        buf = generate_pdf_from_html(formatted)
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
