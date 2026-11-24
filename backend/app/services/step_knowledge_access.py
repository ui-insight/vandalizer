"""Who may have a workflow step query a knowledge base.

A Knowledge Base Query step names a knowledge base in its settings
(``kb_uuid``) and the run searches it. That follows the same two rules as a
document in a workflow's setup (see ``fixed_document_access``):

* **Saving**: a step can only be pointed at a knowledge base its author can
  open.
* **Running**: the knowledge base is queried only if the person who started
  the run, or the workflow's owner, can open it.

Knowledge base access has more to it than a file's (organizations, verified
items, open reviews), so there is no second copy of the rule for the worker:
everything here goes through ``access_control.get_authorized_knowledge_base``,
and the worker reaches it with ``unreadable_for_run_sync``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from pymongo.database import Database

    from app.models.user import User
    from app.models.workflow import Workflow

KB_TASK_NAME = "KnowledgeBaseQuery"

STEP_KB_ACCESS_MESSAGE = (
    "You don't have access to the knowledge base this step is set to query. "
    "Choose one of your own or one that has been shared with you."
)


def knowledge_bases_denied_message(count: int) -> str:
    """Deliberately names no knowledge base: the reader isn't entitled to its title."""
    one = count == 1
    return (
        f"This workflow has {'a step that queries a knowledge base' if one else f'steps that query {count} knowledge bases'} "
        f"that neither you nor the workflow's owner can open, so the run was stopped before querying "
        f"{'it' if one else 'them'}. Choose a different knowledge base in "
        f"{'that step' if one else 'those steps'}, or ask the owner to share {'it' if one else 'them'}."
    )


def task_kb_uuid(task_name: str | None, task_data: dict | None) -> str | None:
    """The knowledge base a task will query, if it is a Knowledge Base Query."""
    if task_name != KB_TASK_NAME or not isinstance(task_data, dict):
        return None
    uuid = task_data.get("kb_uuid")
    uuid = uuid.strip() if isinstance(uuid, str) else ""
    return uuid or None


def definition_kb_uuids(definition: dict | None) -> list[str]:
    """Knowledge bases queried by the steps of a workflow definition
    (the shape versions and export files store)."""
    uuids: list[str] = []
    for step in (definition or {}).get("steps") or []:
        for task in (step.get("tasks") if isinstance(step, dict) else None) or []:
            if not isinstance(task, dict):
                continue
            # An export file carries the original knowledge base's details
            # beside its id; importing clears the id for the user to choose a
            # local one, so it is never queried.
            if isinstance(task.get("data"), dict) and task["data"].get("_embedded_knowledge_base"):
                continue
            uuid = task_kb_uuid(task.get("name"), task.get("data"))
            if uuid and uuid not in uuids:
                uuids.append(uuid)
    return uuids


async def workflow_kb_uuids(wf: "Workflow") -> list[str]:
    """Knowledge bases the workflow's steps are set to query."""
    from app.models.workflow import WorkflowStep, WorkflowStepTask

    if not wf.steps:
        return []
    steps = await WorkflowStep.find({"_id": {"$in": list(wf.steps)}}).to_list()
    task_ids = [task_id for step in steps for task_id in (step.tasks or [])]
    if not task_ids:
        return []
    uuids: list[str] = []
    for task in await WorkflowStepTask.find({"_id": {"$in": task_ids}}).to_list():
        uuid = task_kb_uuid(task.name, task.data)
        if uuid and uuid not in uuids:
            uuids.append(uuid)
    return uuids


def workflow_kb_uuids_sync(db: "Database[dict]", workflow_doc: dict) -> list[str]:
    """``workflow_kb_uuids`` for the synchronous worker (plain pymongo)."""
    uuids: list[str] = []
    for step_id in workflow_doc.get("steps") or []:
        step = db.workflow_step.find_one({"_id": step_id}, {"tasks": 1}) or {}
        for task_id in step.get("tasks") or []:
            task = db.workflow_step_task.find_one({"_id": task_id}, {"name": 1, "data": 1}) or {}
            uuid = task_kb_uuid(task.get("name"), task.get("data"))
            if uuid and uuid not in uuids:
                uuids.append(uuid)
    return uuids


async def unreadable_kbs(kb_uuids: Iterable[str], users: Iterable["User"]) -> list[str]:
    """Which of *kb_uuids* exist and none of *users* may open.

    One that no longer exists is not listed: the step itself reports a
    missing knowledge base when it runs.
    """
    from app.models.knowledge import KnowledgeBase
    from app.services.access_control import get_authorized_knowledge_base

    people = list(users)
    denied: list[str] = []
    for kb_uuid in kb_uuids:
        if not await KnowledgeBase.find_one(KnowledgeBase.uuid == kb_uuid):
            continue
        for person in people:
            if await get_authorized_knowledge_base(kb_uuid, person, allow_admin=True):
                break
        else:
            denied.append(kb_uuid)
    return denied


async def ensure_kb_readable(kb_uuid: str | None, user: "User") -> None:
    """Refuse a knowledge base *user* cannot open. A missing id is refused the
    same way, so the answer never says whether one exists."""
    from app.services.access_control import get_authorized_knowledge_base
    from app.services.workflow_service import FixedDocumentAccessError

    if kb_uuid and not await get_authorized_knowledge_base(kb_uuid, user, allow_admin=True):
        raise FixedDocumentAccessError(STEP_KB_ACCESS_MESSAGE)


async def ensure_task_kb_readable(
    task_name: str | None, task_data: dict | None, user: "User", *,
    already_name: str | None = None, already_data: dict | None = None,
) -> None:
    """The save-time check for one task. A knowledge base the task already
    queried is left alone, so editing its other settings isn't blocked by a
    choice its author made."""
    kb_uuid = task_kb_uuid(task_name, task_data)
    if kb_uuid and kb_uuid != task_kb_uuid(already_name, already_data):
        await ensure_kb_readable(kb_uuid, user)


async def ensure_definition_kbs_readable(
    definition: dict | None, user: "User", *, already: Iterable[str] = (),
) -> None:
    """The save-time check for a whole definition written at once (an import
    into a workflow, a restored version)."""
    kept = set(already)
    for kb_uuid in definition_kb_uuids(definition):
        if kb_uuid not in kept:
            await ensure_kb_readable(kb_uuid, user)


async def _people(user_ids: Iterable[str | None], known: "User | None" = None) -> list["User"]:
    from app.models.user import User

    people: dict[str, User] = {}
    if known is not None:
        people[known.user_id] = known
    for user_id in user_ids:
        if user_id and user_id not in people:
            found = await User.find_one(User.user_id == user_id)
            if found:
                people[user_id] = found
    return list(people.values())


async def ensure_kbs_runnable(wf: "Workflow", user: "User | None", user_id: str | None) -> None:
    """Refuse to start a run that would query a knowledge base neither its
    starter nor the workflow's owner can open."""
    from app.services.workflow_service import FixedDocumentAccessError

    kb_uuids = await workflow_kb_uuids(wf)
    if not kb_uuids:
        return
    denied = await unreadable_kbs(kb_uuids, await _people([user_id, wf.user_id], user))
    if denied:
        raise FixedDocumentAccessError(knowledge_bases_denied_message(len(denied)))


async def ensure_workflow_kbs_runnable(workflow_id: str, user: "User | None", user_id: str | None) -> None:
    """``ensure_kbs_runnable`` for a caller that holds only the workflow's id."""
    from beanie import PydanticObjectId

    from app.models.workflow import Workflow

    wf = await Workflow.get(PydanticObjectId(workflow_id))
    if wf is not None:
        await ensure_kbs_runnable(wf, user, user_id)


def unreadable_for_run_sync(kb_uuids: list[str], user_ids: Iterable[str | None]) -> list[str]:
    """``unreadable_kbs`` for the synchronous worker: the knowledge bases a
    run may not query, given who started it and who owns the workflow.

    Nothing is opened when the workflow queries no knowledge base, which is
    the usual case.
    """
    if not kb_uuids:
        return []
    ids = list(user_ids)

    async def _check() -> list[str]:
        from app.config import Settings
        from app.database import init_db

        await init_db(Settings(), skip_indexes=True)
        return await unreadable_kbs(kb_uuids, await _people(ids))

    from app.tasks import run_task_async

    return run_task_async(_check())
