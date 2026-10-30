"""Reuse existing workspace documents in projects without uploading copies."""

import logging

from pydantic_ai import RunContext

from app.services import access_control, file_service, project_service
from app.services.chat_deps import AgenticChatDeps

logger = logging.getLogger(__name__)


async def list_projects(context: RunContext[AgenticChatDeps], search: str = "") -> list[dict]:
    """Find accessible projects by name before moving existing files into one.

    Use the returned UUID, the active project UUID, or create_project's result.
    Never guess a destination UUID from a title.
    """
    projects = await project_service.list_projects(context.deps.user)
    query = search.strip().casefold()
    return [
        {"uuid": project.uuid, "title": project.title, "root_folder_uuid": project.root_folder_uuid}
        for project in projects if not query or query in project.title.casefold()
    ][:50]


async def move_documents_to_project(
    context: RunContext[AgenticChatDeps],
    project_uuid: str | None = None,
    document_uuids: list[str] | None = None,
    confirmed: bool = False,
) -> dict:
    """Move existing Vandalizer files into a project, preserving their UUIDs.

    This moves files out of their current folders; it does not upload or copy.
    Project members gain access and project knowledge-base indexing runs
    asynchronously. Call with confirmed=false to preview the files and project;
    call with confirmed=true only after the user approves on a later turn.
    Source management and destination write access are required. Moving across
    personal/team ownership boundaries is unsupported; never offer to bypass it.

    project_uuid defaults to the active project. For a newly created project use
    create_project's returned UUID; find other projects with list_projects.
    document_uuids defaults to the files attached to this chat. For other files,
    use search_documents first. Chat attachment alone does not move a file.
    """
    from app.services.chat_tools import _confirm_gate, _resolve_doc_uuids

    user = context.deps.user
    target_uuid = project_uuid or context.deps.active_project_uuid
    if not target_uuid:
        return {"error": "Choose a project first. Use list_projects to find its UUID."}
    project = await project_service.get_authorized_project(target_uuid, user)
    if not project:
        return {"error": "Project not found or not accessible."}
    folder = await access_control.get_authorized_folder(project.root_folder_uuid, user, contribute=True)
    if not folder:
        return {"error": "You do not have permission to add files to this project."}
    uuids = _resolve_doc_uuids(context, document_uuids)
    if not uuids or len(uuids) > 100:
        return {"error": "Choose between 1 and 100 existing files. Use the attached files or search_documents."}

    documents = []
    for uuid in sorted(uuids):
        doc = await access_control.get_authorized_document(uuid, user, manage=True)
        if not doc:
            return {"error": "One or more files are unavailable or you do not have permission to move them. No files were moved."}
        if doc.team_id != folder.team_id:
            return {"error": "Cannot move files between personal and team folders or different teams. No files were moved."}
        documents.append(doc)

    moving = [doc for doc in documents if doc.folder != folder.uuid]
    already = [{"uuid": doc.uuid, "title": doc.title} for doc in documents if doc.folder == folder.uuid]
    if not moving:
        return {"status": "completed", "project_uuid": project.uuid, "moved_documents": [], "already_in_project": already, "message": "These files are already in the project's root folder. No files were moved."}

    # Bind approval to the destination and current source locations as well as
    # file IDs. A changed selection or a file moved since preview needs approval.
    gate = await _confirm_gate(
        context,
        tool_name="move_documents_to_project",
        key={
            "project_uuid": project.uuid,
            "folder_uuid": folder.uuid,
            "documents": [{"uuid": doc.uuid, "folder": doc.folder, "title": doc.title} for doc in documents],
        },
        confirmed=confirmed,
        preview={
            "action": "move_documents_to_project",
            "approval_label": "Move files",
            "project_uuid": project.uuid,
            "documents": [{"uuid": doc.uuid, "title": doc.title} for doc in moving],
            "preview": (
                f'Move {len(moving)} file(s) into project "{project.title}": '
                + ", ".join(doc.title for doc in moving)
                + ". They will leave their current folders and become available to people who can access this project. "
                "The same files and UUIDs are retained; no duplicates are created. Project indexing runs in the background."
            ),
        },
    )
    if gate is not None:
        return gate

    moved, failed = [], []
    for doc in moving:
        item = {"uuid": doc.uuid, "title": doc.title}
        try:
            if await file_service.move_document(doc.uuid, folder.uuid, user=user):
                moved.append(item)
            else:
                failed.append({**item, "error": "File or destination no longer accessible."})
        except ValueError as error:
            failed.append({**item, "error": str(error)})
        except Exception:
            logger.exception("Failed to move document %s into project %s", doc.uuid, project.uuid)
            failed.append({**item, "error": "Move could not be confirmed. Check the project's Files before retrying."})
    return {
        "status": "partial" if moved and failed else "failed" if failed else "completed",
        "project_uuid": project.uuid,
        "moved_documents": moved,
        "failed_documents": failed,
        "already_in_project": already,
        "message": f'Moved {len(moved)} of {len(moving)} files into "{project.title}".' + (
            " Some moves could not be confirmed; check failed_documents and the project's Files before retrying."
            if failed else " Project indexing runs in the background."
        ),
    }
