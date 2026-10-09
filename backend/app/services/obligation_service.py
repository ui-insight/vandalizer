"""The RA inbox: obligations found in a project's documents (#999).

Every obligation is checked against the document it cites before it is saved:
its quote must be on the cited page, a deadline's date must be in its quote,
and a limit's figures must be in their quotes. A proposal that fails is
returned with the reason, never saved, so the inbox cannot hold a deadline
the documents don't state.
"""

import datetime
import re
import uuid as uuid_mod
from typing import Any, Optional

from app.models.document import SmartDocument
from app.models.obligation import (
    DEADLINE_TYPES,
    OBLIGATION_KINDS,
    Obligation,
    ObligationSource,
)
from app.models.project import Project
from app.models.user import User

_MONTHS = {
    m: i for i, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")],
        start=1,
    ) for m in names
}
_DATE_IN_TEXT = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})\b"
    r"|\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b",
    re.IGNORECASE,
)
_MAX_ITEMS = 25


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dates_in(text: str) -> set[tuple[int, int]]:
    """(month, day) pairs written in *text*: "Nov 19", "11/19/2026", "2026-11-19"."""
    found: set[tuple[int, int]] = set()
    for m in _DATE_IN_TEXT.finditer(text or ""):
        if m.group(1):
            found.add((_MONTHS[m.group(1).lower()], int(m.group(2))))
        elif m.group(3):
            found.add((int(m.group(3)), int(m.group(4))))
        elif m.group(6):
            found.add((int(m.group(7)), int(m.group(8))))
    return found


def _parse_due(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.datetime.combine(datetime.date.fromisoformat(text[:10]), datetime.time())
        except ValueError:
            return None


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[,$\s%]", "", value)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _figures_in(text: str) -> set[float]:
    from app.services.kb_answer_grounding import _money_values, _percent_values

    values = set(_money_values(text)) | set(_percent_values(text))
    for m in re.finditer(r"(?<![\w.$])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w%])", text or ""):
        values.add(float(m.group(0).replace(",", "")))
    return values


def _page_text(doc: SmartDocument, page: Optional[int]) -> tuple[Optional[str], Optional[int]]:
    """The cited page's text (widened by a page for interpolated OCR pages),
    or the whole document when it has no page markers. Returns (text, page)."""
    from app.services.chat_service import _page_positions

    raw = doc.raw_text or ""
    positions = _page_positions(getattr(doc, "text_markers", None), len(raw))
    if not positions:
        return raw, None
    if page is None:
        return None, None
    pages = [p for _o, p, _a in positions]
    if page not in pages:
        return None, page
    i = pages.index(page)
    approximate = positions[i][2]
    lo = positions[max(0, i - 1)][0] if approximate else positions[i][0]
    hi_index = i + 2 if approximate else i + 1
    hi = positions[hi_index][0] if hi_index < len(positions) else len(raw)
    return raw[lo:hi], page


async def _readable_document(document_uuid: str, user: User, project: Project) -> Optional[SmartDocument]:
    """The cited document, if this user may read it (project files included)."""
    from app.services import access_control

    return await access_control.get_authorized_document(document_uuid, user)


async def _check_source(raw: dict, user: User, project: Project) -> tuple[Optional[ObligationSource], str | None]:
    from app.services.extraction_sources import find_quote_offset

    if not isinstance(raw, dict):
        return None, "a source must be an object with document_uuid, page and quote"
    quote = str(raw.get("quote") or "").strip()
    document_uuid = str(raw.get("document_uuid") or "").strip()
    if not document_uuid or not quote:
        return None, "every source needs a document_uuid and the exact quote"
    doc = await _readable_document(document_uuid, user, project)
    if doc is None:
        return None, f"document {document_uuid} was not found or you can't open it"
    page = raw.get("page") if isinstance(raw.get("page"), int) else None
    text, page = _page_text(doc, page)
    if text is None:
        return None, (
            f'"{doc.title}" has page numbers; give the page the quote is on'
            if page is None else f'"{doc.title}" has no page {page}'
        )
    if find_quote_offset(text, quote) is None:
        where = f"page {page} of " if page is not None else ""
        return None, f'the quote was not found on {where}"{doc.title}"'
    return ObligationSource(
        document_uuid=doc.uuid, document_title=doc.title or "", page=page,
        quote=quote, role=str(raw.get("role") or "evidence"),
    ), None


async def check_proposal(item: dict, user: User, project: Project) -> tuple[Optional[dict], str | None]:
    """A proposed obligation, checked against its sources.

    Returns ``(clean_item, None)`` or ``(None, reason)``. ``clean_item`` holds
    the validated fields and ``ObligationSource`` objects ready to save.
    """
    if not isinstance(item, dict):
        return None, "each obligation must be an object"
    kind = item.get("kind")
    if kind not in OBLIGATION_KINDS:
        return None, f"kind must be one of {', '.join(OBLIGATION_KINDS)}"
    title = str(item.get("title") or "").strip()
    if not title:
        return None, "a title is required"
    raw_sources = item.get("sources") or []
    if not isinstance(raw_sources, list) or not raw_sources:
        return None, "at least one source (document, page and quote) is required"
    sources: list[ObligationSource] = []
    for raw in raw_sources[:4]:
        src, reason = await _check_source(raw, user, project)
        if reason:
            return None, reason
        sources.append(src)
    quotes = " ".join(s.quote for s in sources)
    clean: dict[str, Any] = {"kind": kind, "title": title[:200], "sources": sources}

    if kind == "deadline":
        deadline_type = item.get("deadline_type") or "other"
        if deadline_type not in DEADLINE_TYPES:
            return None, f"deadline_type must be one of {', '.join(DEADLINE_TYPES)}"
        due = _parse_due(item.get("due_at"))
        if due is None:
            return None, "a deadline needs due_at as an ISO date (2026-11-19 or 2026-11-19T17:00)"
        if (due.month, due.day) not in _dates_in(quotes):
            return None, f"the quote does not state {due:%B} {due.day}; cite the passage that gives the date"
        clean.update(deadline_type=deadline_type, due_at=due, due_text=str(item.get("due_text") or "")[:120] or None)
    elif kind == "limit":
        limit_value = _as_number(item.get("limit_value"))
        observed = _as_number(item.get("observed_value"))
        if limit_value is None or observed is None:
            return None, "a limit needs limit_value and observed_value as numbers"
        by_role = {s.role: s.quote for s in sources}
        if limit_value not in _figures_in(by_role.get("limit", quotes)):
            return None, "the limit's quote does not state the limit value"
        if observed not in _figures_in(by_role.get("observed", quotes)):
            return None, "the observed value is not stated in its quote"
        clean.update(limit_value=limit_value, observed_value=observed, unit=str(item.get("unit") or "")[:20] or None)
    return clean, None


async def find_replaced(project_uuid: str, clean: dict) -> Optional[Obligation]:
    """The open deadline of the same type a new one would replace (an amendment)."""
    if clean.get("kind") != "deadline" or clean.get("deadline_type") == "other":
        return None
    existing = await Obligation.find(
        Obligation.project_uuid == project_uuid,
        Obligation.kind == "deadline",
        Obligation.deadline_type == clean["deadline_type"],
        Obligation.status == "open",
    ).to_list()
    for ob in existing:
        if ob.due_at and clean.get("due_at") and ob.due_at.date() != clean["due_at"].date():
            return ob
    return None


async def is_duplicate(project_uuid: str, clean: dict) -> bool:
    existing = await Obligation.find(
        Obligation.project_uuid == project_uuid,
        Obligation.kind == clean["kind"],
        Obligation.status == "open",
    ).to_list()
    for ob in existing:
        if clean["kind"] == "deadline" and ob.due_at and clean.get("due_at"):
            if ob.deadline_type == clean.get("deadline_type") and ob.due_at.date() == clean["due_at"].date():
                return True
        elif ob.title.strip().lower() == clean["title"].strip().lower():
            return True
    return False


async def save_checked(project: Project, user: User, clean: dict) -> Obligation:
    replaced = await find_replaced(project.uuid, clean)
    ob = Obligation(
        uuid=uuid_mod.uuid4().hex,
        project_uuid=project.uuid,
        team_id=project.team_id,
        created_by=user.user_id,
        supersedes=replaced.uuid if replaced else None,
        **clean,
    )
    await ob.insert()
    if replaced:
        replaced.status = "superseded"
        replaced.superseded_by = ob.uuid
        replaced.updated_at = _now()
        await replaced.save()
    return ob


async def propose(project: Project, user: User, items: list[dict]) -> dict:
    """Check proposed obligations without saving: what would be added, replaced or rejected."""
    accepted, rejected = [], []
    for item in (items or [])[:_MAX_ITEMS]:
        clean, reason = await check_proposal(item, user, project)
        title = str((item or {}).get("title") or "") if isinstance(item, dict) else ""
        if reason:
            rejected.append({"title": title, "reason": reason})
            continue
        if await is_duplicate(project.uuid, clean):
            rejected.append({"title": clean["title"], "reason": "already in this project's inbox"})
            continue
        replaced = await find_replaced(project.uuid, clean)
        accepted.append({"clean": clean, "replaces": serialize(replaced, user) if replaced else None})
    return {"accepted": accepted, "rejected": rejected}


def _sort_key(ob: Obligation):
    far = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    due = ob.due_at.replace(tzinfo=ob.due_at.tzinfo or datetime.timezone.utc) if ob.due_at else far
    rank = 0 if ob.kind == "deadline" else 1 if ob.in_conflict else 2
    return (rank, due, ob.created_at)


def serialize(ob: Obligation, user: User, project_title: str | None = None) -> dict:
    return {
        "uuid": ob.uuid,
        "project_uuid": ob.project_uuid,
        "project_title": project_title,
        "kind": ob.kind,
        "title": ob.title,
        "deadline_type": ob.deadline_type,
        "due_at": ob.due_at.isoformat() if ob.due_at else None,
        "due_text": ob.due_text,
        "limit_value": ob.limit_value,
        "observed_value": ob.observed_value,
        "unit": ob.unit,
        "in_conflict": ob.in_conflict,
        "sources": [s.model_dump() for s in ob.sources],
        "status": ob.status,
        "supersedes": ob.supersedes,
        "superseded_by": ob.superseded_by,
        "dismissed": user.user_id in (ob.dismissed_by or []),
    }


async def inbox(user: User, *, include_dismissed: bool = False) -> list[dict]:
    """Open obligations across every project *user* can see, for Home."""
    from app.services.project_service import list_projects

    projects = {p.uuid: p for p in await list_projects(user) if p.state != "archived"}
    if not projects:
        return []
    obligations = await Obligation.find(
        {"project_uuid": {"$in": list(projects)}, "status": "open"},
    ).to_list()
    if not include_dismissed:
        obligations = [o for o in obligations if user.user_id not in (o.dismissed_by or [])]
    obligations.sort(key=_sort_key)
    return [serialize(o, user, projects[o.project_uuid].title) for o in obligations]


async def project_obligations(project: Project, user: User) -> list[dict]:
    obligations = await Obligation.find(Obligation.project_uuid == project.uuid).to_list()
    obligations.sort(key=lambda o: ({"open": 0, "done": 1, "superseded": 2}.get(o.status, 3), _sort_key(o)))
    return [serialize(o, user, project.title) for o in obligations]


async def set_done(ob: Obligation, user: User, done: bool) -> Obligation:
    ob.status = "done" if done else "open"
    ob.completed_by = user.user_id if done else None
    ob.completed_at = _now() if done else None
    ob.updated_at = _now()
    await ob.save()
    return ob


async def set_dismissed(ob: Obligation, user: User, dismissed: bool) -> Obligation:
    """Hide or restore an obligation on this user's Home only."""
    others = [u for u in (ob.dismissed_by or []) if u != user.user_id]
    ob.dismissed_by = others + ([user.user_id] if dismissed else [])
    ob.updated_at = _now()
    await ob.save()
    return ob
