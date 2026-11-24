"""Award snapshot: where a project's award stands, from the project's own data.

Support ticket: a project held an award's documents, RA inbox deadlines,
extraction runs and pages, but nothing showed where the award stood. The
overview counted files and tools; "Summarize this project" read only the
document; a saved page was a fixed copy that went stale as soon as a deadline
was marked Done.

The snapshot has two halves with different lifetimes:

* **Facts and budget** — sponsor, award and subaward numbers, PI(s), period,
  total, F&A rate, and the amount per budget year — are read from the
  project's documents by the extraction engine with source capture, so each
  carries its document, page, passage and support state. That costs a model
  call, so the first build is asked for, and later builds happen when the
  project's documents change (a document added or re-read) or on Refresh.
* **Deadlines, status, last run and saved pages** are read live every time
  the snapshot is shown. Marking a deadline Done shows at once.

A fact the passage doesn't confirm is kept, but marked: the reader sees the
value and that it isn't confirmed, never a confident badge it didn't earn.
"""

from __future__ import annotations

import datetime
import hashlib
import html
import logging
import uuid as uuid_mod
from typing import Any

from app.models.award_snapshot import AwardSnapshot, SnapshotFact
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)

# (key, label, what the extraction should look for). Keys are what the
# engine is asked for, so they read as field names in the prompt.
FACT_FIELDS: list[tuple[str, str, str]] = [
    ("Sponsor", "Sponsor",
     "The funding agency or sponsor of the award. For a subaward, the prime (federal) sponsor, e.g. National Institutes of Health."),
    ("Pass-through entity", "Pass-through entity",
     "For a subaward only: the organization issuing the subaward (the prime recipient)."),
    ("Award number", "Award number",
     "The sponsor's award, grant or prime award number."),
    ("Subaward number", "Subaward number",
     "The subaward or subcontract number, if this is a subaward."),
    ("Principal investigator(s)", "PI(s)",
     "The principal investigator(s) named for this award, with institution when stated."),
    ("Period of performance start", "Period start",
     "The start date of the period of performance or project period."),
    ("Period of performance end", "Period end",
     "The end date of the period of performance or project period."),
    ("Total award amount", "Total amount",
     "The total amount of the award or subaward over all budget periods, in dollars."),
    ("F&A rate", "F&A rate",
     "The facilities and administrative (indirect) cost rate and its base, e.g. 52% MTDC."),
]
BUDGET_YEARS = 5
MAX_DOCUMENTS = 6
# Titles that usually hold the award's terms; read first.
_AWARD_WORDS = ("award", "subaward", "agreement", "notice", "noa", "contract", "budget", "amendment", "modification")


def _budget_key(year: int) -> str:
    return f"Budget period {year} amount"


def field_metadata() -> list[dict[str, Any]]:
    meta = [{"key": key, "description": desc, "is_optional": True} for key, _label, desc in FACT_FIELDS]
    meta += [
        {"key": _budget_key(y), "is_optional": True,
         "description": f"The total amount for budget period (budget year) {y} only, in dollars, from the award's budget."}
        for y in range(1, BUDGET_YEARS + 1)
    ]
    return meta


def extract_keys() -> list[str]:
    return [m["key"] for m in field_metadata()]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

_ORIGINAL_FORMATS = ("pdf", "docx", "doc")
# Formats Vandalizer saves summaries in. A file in one of these whose name
# reads like a summary, saved before ``generated_by`` existed, is treated as
# Vandalizer's too.
_TEXT_FORMATS = ("md", "markdown", "txt", "html", "htm")
_SUMMARY_WORDS = ("snapshot", "summary")
# Fields the reader needs to see Vandalizer-written files and the read order.
DOC_FIELDS = {"uuid": 1, "title": 1, "token_count": 1, "updated_at": 1,
              "extension": 1, "generated_by": 1, "origin_workflow_id": 1}


def is_generated(doc: dict) -> bool:
    """Whether *doc* is a file Vandalizer wrote (a summary or report), not an original.

    Support ticket: with the award PDF and a chat-saved "Award Snapshot —
    ….md" in one project, every key fact cited the summary. A summary citing
    a summary isn't a source an RA can review.
    """
    if doc.get("generated_by") or doc.get("origin_workflow_id"):
        return True
    ext = (doc.get("extension") or "").lower().lstrip(".")
    title = (doc.get("title") or "").lower()
    return ext in _TEXT_FORMATS and any(w in title for w in _SUMMARY_WORDS)


def _rank(doc: dict) -> tuple[int, int, str]:
    """Award-like titles first, then the formats awards come in."""
    title = (doc.get("title") or "").lower()
    ext = (doc.get("extension") or "").lower().lstrip(".")
    return (0 if any(w in title for w in _AWARD_WORDS) else 1, 0 if ext in _ORIGINAL_FORMATS else 1, title)


def source_documents(docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """``(read, skipped)``: the documents facts are read from, in order.

    The originals, when the project has any; files Vandalizer wrote are then
    skipped, so a fact missing from the award is reported missing, never
    filled from a summary. Only when the project holds nothing but such files
    are they read.
    """
    ordered = sorted(docs, key=_rank)
    originals = [d for d in ordered if not is_generated(d)]
    if not originals:
        return ordered, []
    return originals, [d for d in ordered if is_generated(d)]


def fingerprint(docs: list[dict]) -> str:
    """Changes when a document is added, removed or re-read."""
    parts = sorted(
        f"{d.get('uuid')}:{d.get('token_count') or 0}:{d.get('updated_at')}" for d in docs
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


async def project_documents(project: Project) -> list[dict]:
    """The project's documents with readable text, award-like titles first."""
    from app.models.document import SmartDocument
    from app.services.project_service import _project_folder_uuids

    folders = await _project_folder_uuids(project.root_folder_uuid)
    rows = await SmartDocument.get_motor_collection().find(
        {"folder": {"$in": folders}, "soft_deleted": {"$ne": True}, "token_count": {"$gt": 0}},
        DOC_FIELDS,
    ).to_list(length=500)
    return sorted(rows, key=_rank)


# ---------------------------------------------------------------------------
# Building (Celery, sync)
# ---------------------------------------------------------------------------

_SUPPORT_RANK = {"supported": 0, "unassessed": 1, "quote_unsupported": 2, "unverified": 3}


def merge_entities(entities: list[dict]) -> tuple[list[SnapshotFact], list[SnapshotFact]]:
    """The best-supported value for each field across every document.

    *entities* come from ``ExtractionEngine.extract(capture_sources=True)`` in
    document order. Ties keep the earlier document, which is the more
    award-like one (see ``_rank``).
    """
    from app.services.extraction_sources import SOURCE_KEY, _is_not_found, support_state_of

    best: dict[str, tuple[int, SnapshotFact]] = {}
    labels = {key: label for key, label, _ in FACT_FIELDS}
    labels.update({_budget_key(y): f"Year {y}" for y in range(1, BUDGET_YEARS + 1)})
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        sources = entity.get(SOURCE_KEY) or {}
        for key, label in labels.items():
            value = entity.get(key)
            if isinstance(value, (list, dict)):
                value = "; ".join(str(v) for v in value) if isinstance(value, list) else None
            if value is None or _is_not_found(value) or not str(value).strip():
                continue
            raw_src = sources.get(key)
            src: dict[str, Any] = raw_src if isinstance(raw_src, dict) else {}
            support = support_state_of(src) if src else "unverified"
            fact = SnapshotFact(
                key=key, label=label, value=" ".join(str(value).split()),
                document_uuid=src.get("document_uuid"), document_title=src.get("document_title"),
                page=src.get("page") if isinstance(src.get("page"), int) else None,
                page_approximate=bool(src.get("page_approximate")),
                quote=src.get("quote"), support=support,
            )
            rank = _SUPPORT_RANK.get(support, 3)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, fact)
    facts = [best[k][1] for k, _l, _d in FACT_FIELDS if k in best]
    budget = [best[_budget_key(y)][1] for y in range(1, BUDGET_YEARS + 1) if _budget_key(y) in best]
    return facts, budget


def build_sync(project_uuid: str, build_token: str) -> str:
    """Read the facts from the project's documents and store them.

    Returns the final status. A build superseded by a newer request (its
    token no longer matches) writes nothing.
    """
    from app.services.extraction_engine import ExtractionEngine
    from app.services.metering import metered
    from app.tasks import get_sync_db
    from app.tasks.extraction_tasks import _get_user_model_name

    db = get_sync_db()
    snap = db.award_snapshot.find_one({"project_uuid": project_uuid})
    project = db.project.find_one({"uuid": project_uuid})
    if not snap or not project or snap.get("build_token") != build_token:
        return "superseded"

    def finish(fields: dict) -> str:
        result = db.award_snapshot.update_one(
            {"project_uuid": project_uuid, "build_token": build_token}, {"$set": fields},
        )
        return fields.get("status", "ready") if result.matched_count else "superseded"

    folders = _folder_uuids_sync(db, project["root_folder_uuid"])
    docs, skipped = source_documents(list(db.smart_document.find(
        {"folder": {"$in": folders}, "soft_deleted": {"$ne": True}, "token_count": {"$gt": 0}},
        {**DOC_FIELDS, "raw_text": 1, "text_markers": 1},
    )))
    if not docs:
        return finish({"status": "empty", "facts": [], "budget_years": [], "documents": [],
                       "skipped_documents": [], "fingerprint": fingerprint([]), "error": None,
                       "built_at": datetime.datetime.now(datetime.timezone.utc)})
    used = docs[:MAX_DOCUMENTS]
    user_id = snap.get("requested_by") or project.get("owner_user_id")
    sys_cfg = db.system_config.find_one() or {}
    model = _get_user_model_name(user_id, db)
    engine = ExtractionEngine(system_config_doc=sys_cfg)
    try:
        with metered("award_snapshot", user_id=user_id, team_id=project.get("team_id")):
            entities = engine.extract(
                extract_keys(), model=model,
                doc_texts=[d.get("raw_text") or "" for d in used],
                field_metadata=field_metadata(),
                capture_sources=True,
                doc_metadata=[{"uuid": d["uuid"], "title": d.get("title"), "text_markers": d.get("text_markers") or []} for d in used],
            )
    except Exception as e:  # noqa: BLE001 — the snapshot records the failure
        logger.exception("Award snapshot build failed for project %s", project_uuid)
        return finish({"status": "error", "error": _plain_error(e)})
    facts, budget = merge_entities(entities if isinstance(entities, list) else [entities])
    return finish({
        "status": "ready",
        "facts": [f.model_dump() for f in facts],
        "budget_years": [f.model_dump() for f in budget],
        "documents": [{"uuid": d["uuid"], "title": d.get("title"), "generated": is_generated(d)} for d in used],
        "skipped_documents": [{"uuid": d["uuid"], "title": d.get("title")} for d in skipped],
        "fingerprint": fingerprint(docs),
        "model": model,
        "error": None,
        "built_at": datetime.datetime.now(datetime.timezone.utc),
    })


def _plain_error(e: Exception) -> str:
    from app.services.trial_budget import TrialBudgetExceededError

    if isinstance(e, TrialBudgetExceededError):
        return "Your account's token budget is used up, so the documents couldn't be read."
    return "The documents couldn't be read for the snapshot. Try Refresh; if it keeps failing, check the project's documents."


def _folder_uuids_sync(db: Any, root: str) -> list[str]:
    uuids, frontier = [root], [root]
    while frontier:
        frontier = [f["uuid"] for f in db.smart_folder.find({"parent_id": {"$in": frontier}}, {"uuid": 1})]
        uuids.extend(frontier)
    return uuids


def _dispatch(project_uuid: str, token: str, countdown: int = 0) -> None:
    from app.celery_app import celery_app

    celery_app.send_task(
        "tasks.extraction.build_award_snapshot", args=[project_uuid, token],
        queue="workflows", countdown=countdown,
    )


async def request_build(project: Project, user: User) -> AwardSnapshot:
    """Queue a build for *user* (Build snapshot / Refresh)."""
    token = uuid_mod.uuid4().hex
    now = datetime.datetime.now(datetime.timezone.utc)
    coll = AwardSnapshot.get_motor_collection()
    await coll.update_one(
        {"project_uuid": project.uuid},
        {"$set": {"status": "building", "build_token": token, "requested_by": user.user_id,
                  "requested_at": now, "error": None},
         "$setOnInsert": {"project_uuid": project.uuid, "facts": [], "budget_years": [],
                          "documents": [], "created_at": now}},
        upsert=True,
    )
    _dispatch(project.uuid, token)
    snap = await AwardSnapshot.find_one(AwardSnapshot.project_uuid == project.uuid)
    assert snap is not None
    return snap


# Debounce for rebuilds triggered by document changes: an upload of several
# files rebuilds once, after the last one is read.
REBUILD_DELAY_SECONDS = 120


def queue_rebuild_for_document_sync(db: Any, document: dict) -> bool:
    """After a document in a project is read: rebuild that project's snapshot.

    Only for a snapshot someone already built — the first build is asked for.
    Never raises; a snapshot must not fail a document's ingestion.
    """
    try:
        from app.tasks.document_tasks import _find_project_for_folder

        project = _find_project_for_folder(db, document.get("folder"))
        if not project:
            return False
        if is_generated(document) and db.smart_document.find_one(
            {"folder": {"$in": _folder_uuids_sync(db, project["root_folder_uuid"])},
             "soft_deleted": {"$ne": True}, "token_count": {"$gt": 0},
             "generated_by": None, "origin_workflow_id": None,
             "extension": {"$nin": list(_TEXT_FORMATS)}},
            {"_id": 1},
        ):
            # A summary saved next to the award isn't read, so it can't change the facts.
            return False
        snap = db.award_snapshot.find_one({"project_uuid": project["uuid"]}, {"built_at": 1})
        if not snap or not snap.get("built_at"):
            return False
        token = uuid_mod.uuid4().hex
        db.award_snapshot.update_one(
            {"project_uuid": project["uuid"]},
            {"$set": {"status": "building", "build_token": token,
                      "requested_at": datetime.datetime.now(datetime.timezone.utc), "error": None}},
        )
        _dispatch(project["uuid"], token, countdown=REBUILD_DELAY_SECONDS)
        return True
    except Exception:
        logger.exception("Could not queue an award snapshot rebuild for %s", document.get("uuid"))
        return False


# ---------------------------------------------------------------------------
# The live view
# ---------------------------------------------------------------------------

def _iso(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.isoformat()


async def _deadlines(project: Project, user: User) -> dict[str, Any]:
    from app.models.obligation import Obligation
    from app.services.deadline_reminders import due_date, today_local
    from app.services.obligation_service import serialize

    today = today_local()
    obligations = await Obligation.find(Obligation.project_uuid == project.uuid).to_list()
    upcoming: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    needed: list[dict[str, Any]] = []
    for ob in obligations:
        row = serialize(ob, user, project.title)
        day = due_date(ob)
        if ob.kind == "deadline" and ob.status == "done":
            done.append(row)
        elif ob.status != "open":
            continue
        elif ob.kind == "deadline" and day is not None:
            row["days_until"] = (day - today).days
            (overdue if day < today else upcoming).append(row)
        else:
            needed.append(row)
    upcoming.sort(key=lambda r: r["due_at"] or "")
    overdue.sort(key=lambda r: r["due_at"] or "")
    done.sort(key=lambda r: r.get("due_at") or "", reverse=True)
    return {"upcoming": upcoming, "overdue": overdue, "done": done, "needed": needed}


async def _activity(project: Project, user: User) -> dict[str, Any]:
    from app.models.activity import ActivityEvent
    from app.models.artifact import Artifact
    from app.models.project import ProjectPin

    last = await ActivityEvent.find(
        {"project_uuid": project.uuid, "type": {"$in": ["workflow_run", "search_set_run"]}},
    ).sort("-started_at").first_or_none()
    # A pinned Page is listed only for someone who can open it: a pin never
    # grants access to what it points at.
    from fastapi import HTTPException

    from app.services.project_service import authorize_resource

    pinned = []
    for pin in await ProjectPin.find({"project_uuid": project.uuid, "pin_type": "artifact"}).to_list():
        try:
            await authorize_resource("artifact", pin.target_id, user)
        except HTTPException:
            continue
        pinned.append(pin.target_id)
    pages = await Artifact.find(
        {"deleted_at": None, "$or": [{"project_uuid": project.uuid}, {"uuid": {"$in": pinned}}]},
    ).sort("-updated_at").limit(5).to_list()
    return {
        "last_run": {
            "title": last.title, "type": last.type, "status": last.status,
            "at": _iso(last.finished_at or last.started_at),
        } if last else None,
        "pages": [{"uuid": p.uuid, "title": p.title or "Untitled page", "updated_at": _iso(p.updated_at)} for p in pages],
    }


async def view(project: Project, user: User) -> dict[str, Any]:
    """The snapshot as shown: stored facts plus everything read live."""
    from app.services.project_service import can_manage_project

    snap = await AwardSnapshot.find_one(AwardSnapshot.project_uuid == project.uuid)
    docs = await project_documents(project)
    current = fingerprint(source_documents(docs)[0])
    built = snap is not None and snap.built_at is not None
    found = {f.key for f in snap.facts} if snap else set()
    return {
        "project": {"uuid": project.uuid, "title": project.title, "state": project.state},
        "status": snap.status if snap else "not_built",
        "facts": [f.model_dump() for f in snap.facts] if snap else [],
        "budget_years": [f.model_dump() for f in snap.budget_years] if snap else [],
        "documents_read": snap.documents if snap else [],
        "documents_skipped": snap.skipped_documents if snap else [],
        # Key facts the documents read don't state: shown as not stated,
        # never filled from elsewhere.
        "not_found": [label for key, label, _ in FACT_FIELDS if key not in found]
        if snap and snap.status == "ready" else [],
        "document_count": len(docs),
        "built_at": _iso(snap.built_at) if snap else None,
        "error": snap.error if snap else None,
        # The documents changed since the facts were read, and no rebuild is
        # already on its way.
        "out_of_date": bool(built and snap and snap.fingerprint != current and snap.status != "building"),
        "page_uuid": snap.page_uuid if snap else None,
        "can_manage": await can_manage_project(project, user),
        "deadlines": await _deadlines(project, user),
        **await _activity(project, user),
        "generated_at": _iso(datetime.datetime.now(datetime.timezone.utc)),
    }


# ---------------------------------------------------------------------------
# Share as Page
# ---------------------------------------------------------------------------

_SUPPORT_NOTE = {
    "supported": "",
    "unassessed": " (passage found; check the value)",
    "quote_unsupported": " (not confirmed by the passage)",
    "unverified": " (source not found)",
}


def _where(f: dict) -> str:
    if not f.get("document_title"):
        return ""
    page = f.get("page")
    page_text = f", p. {'~' if f.get('page_approximate') else ''}{page}" if page else ""
    return f"{f['document_title']}{page_text}"


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    day = datetime.date.fromisoformat(iso[:10])
    return f"{day.strftime('%b')} {day.day}, {day.year}"


def page_html(v: dict[str, Any]) -> str:
    """The snapshot as a Page. A copy: it says when it was made."""
    e = html.escape
    rows = "".join(
        f"<tr><th scope='row'>{e(f['label'])}</th><td>{e(f['value'])}{e(_SUPPORT_NOTE.get(f['support'], ''))}</td>"
        f"<td>{e(_where(f))}</td></tr>"
        for f in v["facts"]
    ) + "".join(
        f"<tr><th scope='row'>{e(label)}</th><td>Not stated in the documents read</td><td></td></tr>"
        for label in v.get("not_found", [])
    ) or "<tr><td colspan='3'>No key facts read yet.</td></tr>"
    budget = "".join(
        f"<tr><th scope='row'>{e(f['label'])}</th><td>{e(f['value'])}{e(_SUPPORT_NOTE.get(f['support'], ''))}</td><td>{e(_where(f))}</td></tr>"
        for f in v["budget_years"]
    )

    def deadline_rows(items: list[dict], empty: str) -> str:
        if not items:
            return f"<li>{e(empty)}</li>"
        out = []
        for d in items:
            src = d["sources"][0] if d.get("sources") else None
            where = f" · {src['document_title']}{', p. ' + str(src['page']) if src and src.get('page') else ''}" if src else ""
            if d.get("entered_by_hand"):
                # No document behind it; the copy must not read as cited.
                where = " · Added by hand · not checked against a document" + (
                    f" · Source: {d['source_note']}" if d.get("source_note") else "")
            when = _date(d.get("due_at")) + (f", {d['due_text']}" if d.get("due_text") else "")
            out.append(f"<li><strong>{e(d['title'])}</strong> · {e(when)}{e(where)}</li>")
        return "".join(out)

    dl = v["deadlines"]
    state = (v["project"]["state"] or "").replace("_", " ").capitalize()
    last = v.get("last_run")
    last_text = f"{last['title']} · {last['status']} · {_date(last['at'])}" if last else "No runs recorded in this project."
    pages = "".join(f"<li>{e(p['title'])}</li>" for p in v.get("pages", [])) or "<li>None yet.</li>"
    as_of = _date(v["generated_at"])
    return f"""<h1>{e(v['project']['title'])}: award snapshot</h1>
<p><em>As of {e(as_of)}. This page is a copy; open the project in Vandalizer for the live snapshot.
Facts were read from the project's documents{(' on ' + e(_date(v['built_at']))) if v.get('built_at') else ''}; deadlines come from the project's RA inbox.</em></p>
<p><strong>Status:</strong> {e(state)}</p>
<h2>Key facts</h2>
<table><thead><tr><th>Fact</th><th>Value</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>
{f'<h2>Budget by year</h2><table><thead><tr><th>Period</th><th>Amount</th><th>Source</th></tr></thead><tbody>{budget}</tbody></table>' if budget else ''}
<h2>Deadlines (RA inbox)</h2>
<h3>Overdue</h3><ul>{deadline_rows(dl['overdue'], 'Nothing overdue.')}</ul>
<h3>Upcoming</h3><ul>{deadline_rows(dl['upcoming'], 'No upcoming deadlines in the inbox.')}</ul>
<h3>Done</h3><ul>{deadline_rows(dl['done'], 'None marked done yet.')}</ul>
<h2>Activity</h2>
<p><strong>Last run:</strong> {e(last_text)}</p>
<p><strong>Saved pages:</strong></p><ul>{pages}</ul>"""


async def share_as_page(project: Project, user: User) -> dict[str, Any]:
    """Make the snapshot a project Page, or add a revision to the one made before."""
    import anyio
    from fastapi import HTTPException

    from app.services import artifacts
    from app.tasks import get_sync_db

    v = await view(project, user)
    title = f"{project.title} — award snapshot"
    body = page_html(v)
    source = {"kind": "award_snapshot", "project_uuid": project.uuid}
    snap = await AwardSnapshot.find_one(AwardSnapshot.project_uuid == project.uuid)

    def save() -> dict:
        db = get_sync_db()
        existing = db.html_artifacts.find_one({"uuid": snap.page_uuid, "deleted_at": None}) if snap and snap.page_uuid else None
        if existing and existing.get("user_id") == user.user_id:
            try:
                return artifacts.revise(db, existing, title, body, existing["latest_revision"], source)
            except HTTPException as e:
                if e.status_code != 422:  # 422 = the revision cap; start a fresh page
                    raise
        return artifacts.create(db, user.user_id, title, body, uuid_mod.uuid4().hex, source)

    doc = await anyio.to_thread.run_sync(save)
    await AwardSnapshot.get_motor_collection().update_one(
        {"project_uuid": project.uuid},
        {"$set": {"page_uuid": doc["uuid"]},
         "$setOnInsert": {"project_uuid": project.uuid, "status": "empty", "facts": [], "budget_years": [], "documents": []}},
        upsert=True,
    )
    return {"uuid": doc["uuid"], "title": doc.get("title") or title, "revision": doc.get("latest_revision")}
