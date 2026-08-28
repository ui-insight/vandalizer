"""Where a document is used: knowledge bases, extractions, workflows, folder.

A document can be a source in a knowledge base, a test case in an extraction
set, and a fixed or per-step document in a workflow — and until now none of
that was visible from the document itself, which mattered most at deletion.
This module answers "used in" for one document from the reference points
the rest of the code writes:

* ``KnowledgeBaseSource.document_uuid``
* ``ExtractionTestCase.document_uuid``  (grouped by its ``SearchSet``)
* ``Workflow.input_config.fixed_documents[]``  (dicts with ``uuid`` or bare ids)
* ``WorkflowStepTask.data.selected_document_uuid`` /
  ``.template_document_uuid``, resolved task → step → workflow

Read-only. Authorization is the document's: whoever can open the document
can see what references it. Within the caller's own tenants, referencing
objects are listed by title even when the caller could not open them — a
reference to a document you can read is itself a fact about your document,
and hiding it would put the "what depends on this?" question right back
where it was. Objects belonging to a team the caller is not a member of are
left out: a team's workflow and knowledge-base names are that team's.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.folder import SmartFolder
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.search_set import SearchSet
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.services import access_control
from app.services.access_control import TeamAccessContext

logger = logging.getLogger(__name__)

# A folder tree deeper than this is a cycle or corruption, not a hierarchy.
_MAX_FOLDER_DEPTH = 50

# Task-data keys that hold a document reference, with the label shown for them.
STEP_DOCUMENT_KEYS = {
    "selected_document_uuid": "selected document",
    "template_document_uuid": "form template",
}


async def _folder_path(folder_id: str | None) -> list[dict[str, str]]:
    """Root-first list of ``{uuid, title}`` for the folder chain; ``[]`` at root."""
    path: list[dict[str, str]] = []
    seen: set[str] = set()
    current = folder_id
    while current and current != "0" and current not in seen and len(path) < _MAX_FOLDER_DEPTH:
        seen.add(current)
        folder = await SmartFolder.find_one({"uuid": current})
        if not folder:
            break
        path.append({"uuid": folder.uuid, "title": folder.title})
        current = folder.parent_id
    path.reverse()
    return path


def in_caller_tenants(obj: Any, visible_teams: set[str]) -> bool:
    """A referencing object is shown if it is personal (no ``team_id`` — its
    owner needed access to the document to reference it) or belongs to a
    team the caller is a member of. Anything else is another tenant's."""
    team_id = getattr(obj, "team_id", None)
    return not team_id or team_id in visible_teams


async def _knowledge_bases_using(doc_uuid: str, visible_teams: set[str]) -> list[dict[str, Any]]:
    sources = await KnowledgeBaseSource.find({"document_uuid": doc_uuid}).to_list()
    if not sources:
        return []
    kb_uuids = list(dict.fromkeys(s.knowledge_base_uuid for s in sources if s.knowledge_base_uuid))
    kbs = await KnowledgeBase.find({"uuid": {"$in": kb_uuids}}).to_list()
    by_uuid = {kb.uuid: kb for kb in kbs}
    out: list[dict[str, Any]] = []
    for uuid in kb_uuids:
        kb = by_uuid.get(uuid)
        if kb is not None and not in_caller_tenants(kb, visible_teams):
            continue
        out.append({
            "uuid": uuid,
            "title": kb.title if kb else "(knowledge base no longer exists)",
            "exists": kb is not None,
        })
    return out


async def _extractions_using(doc_uuid: str, visible_teams: set[str]) -> list[dict[str, Any]]:
    cases = await ExtractionTestCase.find({"document_uuid": doc_uuid}).to_list()
    if not cases:
        return []
    set_uuids = list(dict.fromkeys(c.search_set_uuid for c in cases if c.search_set_uuid))
    sets = await SearchSet.find({"uuid": {"$in": set_uuids}}).to_list()
    by_uuid = {s.uuid: s for s in sets}
    out: list[dict[str, Any]] = []
    for uuid in set_uuids:
        ss = by_uuid.get(uuid)
        if ss is not None and not in_caller_tenants(ss, visible_teams):
            continue
        out.append({
            "uuid": uuid,
            "title": ss.title if ss else "(extraction no longer exists)",
            "exists": ss is not None,
            "test_cases": [
                {"uuid": c.uuid, "label": c.label}
                for c in cases if c.search_set_uuid == uuid
            ],
        })
    return out


def _fixed_document_uuids(input_config: dict | None) -> set[str]:
    out: set[str] = set()
    for fd in (input_config or {}).get("fixed_documents") or []:
        uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
        if uuid:
            out.add(uuid)
    return out


def build_workflow_entries(
    doc_uuid: str,
    fixed_workflows: list[Any],
    step_workflows: list[Any],
    steps: list[Any],
    tasks: list[Any],
) -> list[dict[str, Any]]:
    """Merge the two ways a workflow can reference a document into one entry
    per workflow, each with the list of ``uses`` — pure, for testing.

    *fixed_workflows*: workflows whose ``input_config`` pins the document.
    *step_workflows* / *steps* / *tasks*: the workflow → step → task chain for
    tasks whose data names the document.
    """
    tasks_by_id = {str(t.id): t for t in tasks}
    steps_by_id = {str(s.id): s for s in steps}
    entries: dict[str, dict[str, Any]] = {}

    def _entry(wf) -> dict[str, Any]:
        key = str(wf.id)
        if key not in entries:
            entries[key] = {"id": key, "name": wf.name, "uses": []}
        return entries[key]

    for wf in fixed_workflows:
        if doc_uuid in _fixed_document_uuids(getattr(wf, "input_config", None)):
            _entry(wf)["uses"].append({"kind": "fixed_document"})

    for wf in step_workflows:
        entry = None
        for step_id in getattr(wf, "steps", None) or []:
            step = steps_by_id.get(str(step_id))
            if not step:
                continue
            for task_id in getattr(step, "tasks", None) or []:
                task = tasks_by_id.get(str(task_id))
                if not task:
                    continue
                data = getattr(task, "data", None) or {}
                for key, label in STEP_DOCUMENT_KEYS.items():
                    if data.get(key) == doc_uuid:
                        entry = entry or _entry(wf)
                        entry["uses"].append({
                            "kind": "step_document",
                            "step": step.name,
                            "task": task.name,
                            "role": label,
                        })
    return list(entries.values())


async def _workflows_using(doc_uuid: str, visible_teams: set[str]) -> list[dict[str, Any]]:
    fixed_workflows = await Workflow.find({
        "$or": [
            {"input_config.fixed_documents.uuid": doc_uuid},
            {"input_config.fixed_documents": doc_uuid},
        ],
    }).to_list()

    tasks = await WorkflowStepTask.find({
        "$or": [{f"data.{key}": doc_uuid} for key in STEP_DOCUMENT_KEYS],
    }).to_list()
    steps: list[Any] = []
    step_workflows: list[Any] = []
    if tasks:
        steps = await WorkflowStep.find({"tasks": {"$in": [t.id for t in tasks]}}).to_list()
        if steps:
            step_workflows = await Workflow.find({"steps": {"$in": [s.id for s in steps]}}).to_list()

    fixed_workflows = [wf for wf in fixed_workflows if in_caller_tenants(wf, visible_teams)]
    step_workflows = [wf for wf in step_workflows if in_caller_tenants(wf, visible_teams)]
    return build_workflow_entries(doc_uuid, fixed_workflows, step_workflows, steps, tasks)


async def document_usage(doc_uuid: str, *, user: User) -> dict[str, Any] | None:
    """Everything that references *doc_uuid*, or None if the caller cannot
    open the document (or it does not exist)."""
    access: TeamAccessContext = await access_control.get_team_access_context(user)
    doc: SmartDocument | None = await access_control.get_authorized_document(
        doc_uuid, user, team_access=access
    )
    if not doc:
        return None

    visible_teams = access.team_uuids | access.team_object_ids
    folder_path = await _folder_path(doc.folder)
    knowledge_bases = await _knowledge_bases_using(doc.uuid, visible_teams)
    extractions = await _extractions_using(doc.uuid, visible_teams)
    workflows = await _workflows_using(doc.uuid, visible_teams)

    return {
        "document": {"uuid": doc.uuid, "title": doc.title},
        "folder": {"path": folder_path, "team_id": doc.team_id},
        "knowledge_bases": knowledge_bases,
        "extractions": extractions,
        "workflows": workflows,
        "total": len(knowledge_bases) + len(extractions) + len(workflows),
    }
