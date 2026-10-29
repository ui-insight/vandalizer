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
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_IN_TEXT = re.compile(
    r"\b(?P<mon>" + _MONTH_NAMES + r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(?P<year>\d{4})\b)?"
    r"|\b(?P<day2>\d{1,2})\s+(?P<mon2>" + _MONTH_NAMES + r")\.?,?(?:\s+(?P<year2>\d{4})\b)?"
    r"|\b(?P<um>\d{1,2})/(?P<ud>\d{1,2})/(?P<uy>\d{2,4})\b"
    r"|\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b",
    re.IGNORECASE,
)
# Generic regional time follows daylight-saving rules. Explicit standard or
# daylight labels keep their stated offset; never silently reinterpret PST as PDT.
_ZONES = {
    "pacific": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "mountain": "America/Denver", "mt": "America/Denver",
    "mst": "America/Denver", "mdt": "America/Denver",
    "central": "America/Chicago", "ct": "America/Chicago",
    "cst": "America/Chicago", "cdt": "America/Chicago",
    "eastern": "America/New_York", "et": "America/New_York",
    "est": "America/New_York", "edt": "America/New_York",
    "alaska": "America/Anchorage", "hawaii": "Pacific/Honolulu",
    "utc": "UTC", "gmt": "UTC",
}
_FIXED_OFFSETS = {"pst": -8, "pdt": -7, "mst": -7, "mdt": -6,
                  "cst": -6, "cdt": -5, "est": -5, "edt": -4}
_STANDARD_OFFSETS = {"pacific": -8, "mountain": -7, "central": -6,
                     "eastern": -5, "alaska": -9, "hawaii": -10}
_TIME_IN_TEXT = re.compile(
    r"(?:\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap])\.?\s?m\b\.?"
    r"|\b(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)\b"
    r"|\b(?P<word>noon|midnight)\b)"
    r"(?:\s*(?:\(|,)?\s*(?:"
    r"(?P<zone>pacific|mountain|central|eastern|alaska|hawaii)(?:\s+(?P<zone_mode>standard|daylight|prevailing))?\s+time"
    r"|(?P<abbr>pt|pst|pdt|mt|mst|mdt|ct|cst|cdt|et|est|edt|utc|gmt)\b"
    r"|(?P<local>local\s+time|submitter'?s\s+local\s+time)))?",
    re.IGNORECASE,
)
_MAX_ITEMS = 25


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _dates_in(text: str) -> set[tuple[Optional[int], int, int]]:
    """(year or None, month, day) for each date written in *text*:
    "Nov 19", "November 19, 2026", "19 November 2026", "11/19/2026", "2026-11-19"."""
    found: set[tuple[Optional[int], int, int]] = set()
    for m in _DATE_IN_TEXT.finditer(text or ""):
        if m.group("mon"):
            year = int(m.group("year")) if m.group("year") else None
            found.add((year, _MONTHS[m.group("mon").lower()], int(m.group("day"))))
        elif m.group("mon2"):
            year = int(m.group("year2")) if m.group("year2") else None
            found.add((year, _MONTHS[m.group("mon2").lower()], int(m.group("day2"))))
        elif m.group("um"):
            year = int(m.group("uy"))
            found.add((year + 2000 if year < 100 else year, int(m.group("um")), int(m.group("ud"))))
        elif m.group("iy"):
            found.add((int(m.group("iy")), int(m.group("im")), int(m.group("id"))))
    return found


def _times_in(text: str) -> list[dict]:
    """Each time of day written in *text*, with its zone when one is stated.

    ``zone`` is an IANA name, ``"local"`` for "local time", or None.
    """
    found: list[dict] = []
    for m in _TIME_IN_TEXT.finditer(text or ""):
        if m.group("word"):
            hour, minute = (12, 0) if m.group("word").lower() == "noon" else (0, 0)
        elif m.group("ap"):
            hour, minute = int(m.group("h")), int(m.group("m") or 0)
            if not 1 <= hour <= 12 or minute > 59:
                continue
            hour = hour % 12 + (12 if m.group("ap").lower() == "p" else 0)
        else:
            hour, minute = int(m.group("h24")), int(m.group("m24"))
        name = (m.group("zone") or m.group("abbr") or "").lower()
        zone = _ZONES.get(name) or ("local" if m.group("local") else None)
        offset = _FIXED_OFFSETS.get(name)
        mode = (m.group("zone_mode") or "").lower()
        if mode in {"standard", "daylight"}:
            offset = _STANDARD_OFFSETS[name] + (1 if mode == "daylight" else 0)
        found.append({"hour": hour, "minute": minute, "zone": zone, "offset": offset, "text": m.group(0).strip()})
    return found


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,()]", "", (text or "").lower())).strip()


def check_deadline(
    due_value: Any, due_text: Any, quotes: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Verify a deadline's full date, and any time and zone, against its quotes.

    Returns ``({"due_at", "due_text"}, None)`` or ``(None, reason)``.
    ``due_at`` is the deadline as the source writes it: the stated date, and
    the stated time if there is one, in the source's own zone, without an
    offset. ``due_text`` is the time as written, taken from the quote. Nothing
    the source doesn't state is filled in: no year, time or zone.
    """
    raw = due_value.isoformat() if isinstance(due_value, datetime.datetime) else due_value
    if not isinstance(raw, str) or not raw.strip():
        return None, "a deadline needs due_at as an ISO date (2026-11-19 or 2026-11-19T17:00)"
    raw = raw.strip()
    due = _parse_due(raw)
    if due is None:
        return None, "a deadline needs due_at as an ISO date (2026-11-19 or 2026-11-19T17:00)"
    has_time = len(raw) > 10
    if due.second or due.microsecond or re.search(r"\b\d{1,2}:\d{2}:\d{2}\b", quotes):
        return None, "deadline precision finer than a minute cannot be verified by this check"
    dates = _dates_in(quotes)
    times = _times_in(quotes)
    time_keys = {(t['hour'], t['minute'], t['zone'], t['offset']) for t in times}
    if times and (len(dates) > 1 or len(time_keys) > 1):
        return None, "the quotes contain multiple dates or times; cite a narrower passage for this deadline so its components cannot be mixed"

    stated_time: Optional[dict] = None
    if has_time:
        if not times:
            return None, (
                "the quote states no time of day; give due_at as a date only "
                f"({due:%Y-%m-%d})"
            )
        if due.tzinfo is not None:
            from zoneinfo import ZoneInfo

            zoned = [t for t in times if t["zone"] and t["zone"] != "local"]
            if not zoned:
                return None, (
                    f"the quote gives {times[0]['text']} without a time zone; give "
                    "due_at without a UTC offset, as the source writes it"
                )
            for t in zoned:
                zone = datetime.timezone(datetime.timedelta(hours=t["offset"])) if t["offset"] is not None else ZoneInfo(t["zone"])
                local = due.astimezone(zone)
                if (local.hour, local.minute) == (t["hour"], t["minute"]):
                    due, stated_time = local.replace(tzinfo=None), t
                    break
            else:
                return None, (
                    f"due_at is not the time the quote states ({zoned[0]['text']})"
                )
        else:
            stated_time = next(
                (t for t in times if (t["hour"], t["minute"]) == (due.hour, due.minute)),
                None,
            )
            if stated_time is None:
                return None, (
                    f"the quote does not state {due:%H:%M}; it gives {times[0]['text']}"
                )

    same_day = [(y, mo, d) for y, mo, d in dates if (mo, d) == (due.month, due.day)]
    if not same_day:
        return None, f"the quote does not state {due:%B} {due.day}; cite the passage that gives the date"
    years = {y for y, _mo, _d in same_day if y is not None}
    if years and due.year not in years:
        return None, (
            f"the quote states {due:%B} {due.day}, {min(years)}, not {due.year}"
        )
    if not years:
        return None, (
            f"the quote gives {due:%B} {due.day} without a year; cite a passage "
            "that explicitly gives the full deadline date, including its year"
        )

    text = str(due_text or "").strip()[:120]
    if text and _normalized(text) not in _normalized(quotes):
        return None, "due_text must be copied from the quote; give the time exactly as written"
    if not has_time and times:
        return None, "the quote states a time of day; include that time in due_at so it is not lost"
    if text and stated_time is not None:
        described = _times_in(text)
        expected = (stated_time['hour'], stated_time['minute'], stated_time['zone'], stated_time['offset'])
        if len(described) != 1 or (described[0]['hour'], described[0]['minute'], described[0]['zone'], described[0]['offset']) != expected:
            return None, "due_text must describe the same verified time and time zone as due_at"
    # Store only the verified time/zone. The date is already in due_at; keeping
    # the model's full "due June 30, 2026" phrase repeats it in every inbox/card.
    text = stated_time["text"] if stated_time is not None else None
    if not has_time:
        due = datetime.datetime.combine(due.date(), datetime.time())
    return {"due_at": due, "due_text": text or None}, None


def _parse_due(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?", text):
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(text)
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
        return None, "the source document was not found or you can't open it"
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
        checked, reason = check_deadline(item.get("due_at"), item.get("due_text"), quotes)
        if reason:
            return None, reason
        clean.update(deadline_type=deadline_type, **checked)
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


async def inbox_projects(user: User) -> dict[str, Project]:
    """The projects Home's inbox covers: every unarchived one *user* can see."""
    from app.services.project_service import list_projects

    return {p.uuid: p for p in await list_projects(user) if p.state != "archived"}


async def inbox(
    user: User,
    *,
    include_dismissed: bool = False,
    projects: dict[str, Project] | None = None,
) -> list[dict]:
    """Open obligations across every project *user* can see, for Home."""
    if projects is None:
        projects = await inbox_projects(user)
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
