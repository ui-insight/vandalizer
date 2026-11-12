"""Workflow steps that act on the workspace: an RA routine in one run.

Support ticket ("RA playbooks"): every new award gets the same steps, create a
project, add the agreement, find the deadlines, pull out the key details, make
a summary page, and asking chat to do them in one go went wrong in order,
duplicates and status. A Workflow already saves steps, runs on a file, is
shared with a team, starts on new files in a watched folder, and has an
Approval Gate; these three steps let it do the RA's part too:

* **Create project**: a project named from the document (or a template), with
  the run's files moved into it. A file already in a project reuses that
  project, so re-running the routine on the same award doesn't make another.
* **Add deadlines to RA inbox**: reads the run's documents for reporting
  deadlines, required material and sponsor limits, then checks every item
  against its quoted page with the same rules as chat's inbox proposals
  (``obligation_service.propose``) and saves the ones that pass. Items already
  in the inbox are skipped; refused ones are listed with the reason.
* **Award snapshot page**: builds the project's award snapshot and saves it as
  a project Page.

Each step's output says exactly what it did, and anything partial is a step
warning ("Completed with warnings"), so the run's step list is the honest
checklist. They act only in real runs: built for a validation run, a step
test or a certification exercise they describe what they would do instead
(``workspace_actions``). Put an Approval Gate in front of them to review once
before anything is created.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")
EARLIER = "_earlier_steps"
# Only a Create project step's own report names the run's project. Any other
# step's text (a prompt's answer, an echoed document) may contain a project
# link too, and must not redirect where later steps write.
PROJECT_LINK = re.compile(r"^(?:Created project|The file is already in project) \[.*?\]\(/\?project=([0-9a-f]{32})\)")
MAX_DEADLINE_ITEMS = 25
_READ_CHARS = 120_000

WORKSPACE_TASKS = frozenset({"CreateProject", "InboxDeadlines", "AwardSnapshotPage"})


def _run(make: Callable[[], Awaitable[T]]) -> T:
    """Run async workspace services from a workflow step's worker thread."""
    from app.config import Settings
    from app.database import init_db
    from app.tasks import run_task_async

    async def go() -> T:
        await init_db(Settings(), skip_indexes=True)
        return await make()

    return run_task_async(go())


def run_documents(inputs: dict) -> list[str]:
    """The run's input files: the Document step's output."""
    for step in inputs.get(EARLIER) or []:
        if isinstance(step, dict) and step.get("name") == "Document" and isinstance(step.get("output"), list):
            return [str(u) for u in step["output"] if u]
    return []


def run_project(inputs: dict) -> Optional[str]:
    """The project an earlier Create project step made (its output links it)."""
    texts = [inputs.get("output")] + [s.get("output") for s in reversed(inputs.get(EARLIER) or []) if isinstance(s, dict)]
    for text in texts:
        match = PROJECT_LINK.match(text) if isinstance(text, str) else None
        if match:
            return match.group(1)
    return None


def _preview(name: str, says: str) -> dict:
    return {"output": f"{says}\n\n_Preview only: workspace changes are made only when the workflow runs for real._",
            "step_name": name}


class _WorkspaceNode:
    """Shared plumbing; concrete steps subclass this with workflow_engine.Node."""

    data: dict
    name: str

    def acting(self) -> bool:
        return bool(self.data.get("_workspace_actions"))

    def has_side_effects(self) -> bool:
        # A failed step that already created a project must not be retried.
        return self.acting()

    async def _user(self) -> Any:
        from app.models.user import User

        user = await User.find_one(User.user_id == self.data.get("user_id"))
        if user is None:
            raise RuntimeError("the user running this workflow was not found")
        return user


# ── Create project ──────────────────────────────────────────────────────────

def project_title(template: str, document_titles: list[str]) -> str:
    """"{document}" → the first file's name without its extension."""
    first = document_titles[0] if document_titles else "New award"
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", first).replace("_", " ").strip() or "New award"
    title = (template or "{document}").replace("{document}", stem).strip()
    return title[:120] or stem[:120]


async def create_project_for(user: Any, doc_uuids: list[str], template: str) -> dict:
    from app.models.project import Project
    from app.services import access_control, file_service, project_service

    documents = []
    for uuid in doc_uuids:
        doc = await access_control.get_authorized_document(uuid, user, manage=True)
        if doc is None:
            raise RuntimeError("a file this run was started on is unavailable, or you can't move it")
        documents.append(doc)
    if not documents:
        raise RuntimeError("no files reached this step; start the workflow on the award's file")

    # Already filed in a project: reuse it rather than make a second one.
    for doc in documents:
        folder = doc.folder
        project = None
        while folder and folder != "0" and project is None:
            project = await Project.find_one(Project.root_folder_uuid == folder)
            if project is None:
                from app.models.folder import SmartFolder
                parent = await SmartFolder.find_one(SmartFolder.uuid == folder)
                folder = parent.parent_id if parent else None
        if project is not None and await project_service.get_authorized_project(project.uuid, user):
            return {"project": project, "created": False, "moved": [], "already": [d.title for d in documents]}

    title = project_title(template, [d.title for d in documents])
    project = await project_service.create_project(title, f"Set up by a workflow from {documents[0].title}.", user)
    moved, failed = [], []
    for doc in documents:
        if doc.team_id is not None:
            failed.append(f"{doc.title} (a team file; projects start personal, so move it by hand)")
            continue
        if await file_service.move_document(doc.uuid, project.root_folder_uuid, user=user):
            moved.append(doc.title)
        else:
            failed.append(doc.title)
    return {"project": project, "created": True, "moved": moved, "failed": failed, "already": []}


def describe_project(result: dict) -> tuple[str, Optional[str]]:
    project = result["project"]
    link = f"[{project.title}](/?project={project.uuid})"
    if not result["created"]:
        return (f"The file is already in project {link}, so it was reused; no new project was created.", None)
    lines = [f"Created project {link}."]
    if result["moved"]:
        lines.append("Added: " + ", ".join(result["moved"]) + ".")
    warning = None
    if result.get("failed"):
        warning = "Not added to the project: " + "; ".join(result["failed"]) + "."
        lines.append(warning)
    return "\n".join(lines), warning


# ── Add deadlines to RA inbox ───────────────────────────────────────────────

class FoundSource(BaseModel):
    page: Optional[int] = Field(default=None, description="Page the quote is on, from the [p. N] markers.")
    quote: str = Field(description="Exact words from the document, copied character for character.")
    role: Literal["evidence", "timing", "period_of_performance", "budget_period", "limit", "observed"] = "evidence"


class FoundItem(BaseModel):
    kind: Literal["deadline", "required_material", "limit"]
    title: str
    deadline_type: Optional[Literal["sponsor_submission", "internal_routing", "report_due", "other"]] = None
    due_at: Optional[str] = Field(default=None, description="ISO date as the quote states it; omit for relative deadlines.")
    due_text: Optional[str] = None
    relative_deadline: bool = False
    limit_value: Optional[float] = None
    observed_value: Optional[float] = None
    unit: Optional[Literal["$", "%"]] = None
    sources: list[FoundSource]


class FoundItems(BaseModel):
    items: list[FoundItem] = Field(default_factory=list)


FIND_PROMPT = """You read award, subaward and solicitation documents for a research administrator and list what the project must do or deliver: reporting deadlines, required material, and sponsor limits.

Rules:
- Only what the document states. Never infer a deadline the text doesn't give; the period of performance itself is not a deadline.
- Every item cites the exact quote it comes from and its page (from the [p. N] markers).
- A deadline with a stated calendar date: give due_at as written (YYYY-MM-DD, plus a time only if the quote states one).
- A deadline stated relative to something ("60 days after the end of each budget period", "120 days after the End Date", "within 30 days of each June 30", "60 days after March 1, 2027"): set relative_deadline true, omit due_at, and give the rule as a source with role "timing" plus the period of performance as a source with role "period_of_performance" (its quoted start and end dates), and each dated budget period with role "budget_period" when the rule uses budget periods. When the dates are in a table, quote the header row with the Start/End Date labels and the row with their dates. Do no date arithmetic yourself.
- Required material (a letter, form, certification, report the award requires): kind "required_material".
- A limit: kind "limit" with the limit (role "limit") and, only if a document states the figure that meets or exceeds it, that figure (role "observed").
- List each distinct obligation once. At most 25 items."""


async def _document_text(doc: Any) -> str:
    from app.services.chat_tools import read_document_range

    parts: list[str] = []
    start_page: Optional[int] = None
    start_char: Optional[int] = None
    while sum(len(p) for p in parts) < _READ_CHARS:
        read = read_document_range(doc.raw_text or "", getattr(doc, "text_markers", None),
                                   start_page=start_page, start_char=start_char)
        if "error" in read:
            break
        parts.append(str(read.get("text") or ""))
        if read.get("complete"):
            break
        start_page, start_char = read.get("next_page"), read.get("next_start_char")
        if start_page is None and start_char is None:
            break
    return "\n".join(parts)


async def find_items(model_name: str, sys_cfg: dict | None, documents: list[Any]) -> list[dict]:
    """The model's candidate inbox items; the server checks every one."""
    from pydantic_ai import Agent

    from app.services.llm_service import get_agent_model

    agent = Agent(get_agent_model(model_name, system_config_doc=sys_cfg), system_prompt=FIND_PROMPT, output_type=FoundItems)
    items: list[dict] = []
    for doc in documents:
        text = await _document_text(doc)
        if not text.strip():
            continue
        result = await agent.run(f"Document: {doc.title}\n\n{text}")
        for item in result.output.items[:MAX_DEADLINE_ITEMS]:
            row = item.model_dump(exclude_none=True)
            row["sources"] = [{**s, "document_uuid": doc.uuid} for s in row["sources"]]
            items.append(row)
    return items[:MAX_DEADLINE_ITEMS]


async def add_deadlines(user: Any, project_uuid: str, doc_uuids: list[str], model_name: str, sys_cfg: dict | None) -> dict:
    from app.services import access_control, obligation_service, project_service

    project = await project_service.get_authorized_project(project_uuid, user)
    if project is None:
        raise RuntimeError("the project from the earlier step is unavailable")
    if not await project_service.can_manage_project(project, user):
        raise RuntimeError("you need edit access to change this project's inbox")
    documents = [d for d in [await access_control.get_authorized_document(u, user) for u in doc_uuids] if d is not None]
    if not documents:
        raise RuntimeError("no readable files reached this step")
    items = await find_items(model_name, sys_cfg, documents)
    checked = await obligation_service.propose(project, user, items)
    saved = [await obligation_service.save_checked(project, user, a["clean"]) for a in checked["accepted"]]
    already = [r for r in checked["rejected"] if "already in this project's inbox" in (r.get("reason") or "")]
    refused = [r for r in checked["rejected"] if r not in already]
    return {"project": project, "found": len(items), "saved": saved, "already": already, "refused": refused}


def describe_deadlines(result: dict) -> tuple[str, Optional[str]]:
    from app.services.chat_tools import _obligation_review_reason

    project = result["project"]
    lines = [f"Added {len(result['saved'])} item{'s' if len(result['saved']) != 1 else ''} to the RA inbox for "
             f"[{project.title}](/?project={project.uuid}):"]
    for ob in result["saved"]:
        due = ob.due_at.date().isoformat() if getattr(ob, "due_at", None) else ""
        calc = getattr(ob, "deadline_calculation", None)
        how = f" ({calc.formula})" if calc is not None else ""
        lines.append(f"- {ob.title}{f': {due}' if due else ''}{how}")
    if not result["saved"]:
        lines.append("- nothing new")
    if result["already"]:
        done = sum("marked done" in (r.get("reason") or "") for r in result["already"])
        lines.append(f"Already in the inbox: {len(result['already'])}" + (f" ({done} marked done)." if done else "."))
    warning = None
    if result["refused"]:
        reasons = [f"{r.get('title') or 'Item'} ({_obligation_review_reason(r.get('reason') or '')})" for r in result["refused"]]
        warning = f"{len(reasons)} item{'s' if len(reasons) != 1 else ''} found but not added, for review: " + "; ".join(reasons)
        lines.append(warning)
    if result["found"] == 0:
        warning = "No deadlines, required material or limits were found in the documents."
        lines.append(warning)
    return "\n".join(lines), warning


# ── Award snapshot page ─────────────────────────────────────────────────────

def snapshot_page(user: Any, project_uuid: str) -> dict:
    import datetime
    import uuid as uuid_mod

    from app.services import award_snapshot
    from app.tasks import get_sync_db

    async def authorize() -> Any:
        from app.services import project_service
        project = await project_service.get_authorized_project(project_uuid, user)
        if project is None:
            raise RuntimeError("the project from the earlier step is unavailable")
        if not await project_service.can_manage_project(project, user):
            raise RuntimeError("you need edit access to build and share this project's snapshot")
        return project

    # Same rule as Build snapshot / Share as Page: check before claiming a build.
    _run(authorize)
    db = get_sync_db()
    token = uuid_mod.uuid4().hex
    db.award_snapshot.update_one(
        {"project_uuid": project_uuid},
        {"$set": {"status": "building", "build_token": token, "requested_by": user.user_id,
                  "requested_at": datetime.datetime.now(datetime.timezone.utc), "error": None},
         "$setOnInsert": {"project_uuid": project_uuid, "facts": [], "budget_years": [], "documents": [],
                          "created_at": datetime.datetime.now(datetime.timezone.utc)}},
        upsert=True,
    )
    status = award_snapshot.build_sync(project_uuid, token)

    async def share() -> dict:
        from app.services import project_service
        project = await project_service.get_authorized_project(project_uuid, user)
        if project is None:
            raise RuntimeError("the project from the earlier step is unavailable")
        return {"page": await award_snapshot.share_as_page(project, user), "project": project}

    shared = _run(share)
    return {"status": status, **shared}


def describe_snapshot(result: dict) -> tuple[str, Optional[str]]:
    page = result["page"]
    text = f"Saved the award snapshot as a Page: [{page['title']}](/pages/{page['uuid']})."
    warning = None
    if result["status"] != "ready":
        warning = f"The snapshot finished as “{result['status']}”: some facts may be missing or unconfirmed; check the Page."
        text += "\n" + warning
    return text, warning
