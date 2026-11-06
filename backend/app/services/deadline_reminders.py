"""Reminders, overdue alerts and calendar files for RA inbox deadlines.

Deadlines found in a project's documents reached the RA inbox on Home and
nowhere else: no bell entry before a due date, nothing when one passed, no
email and no way to put them on a calendar (support ticket). This module adds
all of that on top of the existing pieces: the bell (``notification_service``),
email (``email_service``) and project access (``project_service``).

Who is reminded: the project's owner and the people it is shared with, plus
the admins and owners of a team project's team who turned on reminders for
team projects. Someone who dismissed an item from their Home is not reminded
of it. Only open deadlines with a date in unarchived projects count.

When: before the due date at each configured number of days (14 and 3 by
default), on the due date, and once when it has passed without being marked
Done. A recurring rule is stored as one obligation per occurrence
(``relative_deadlines``), so each occurrence is reminded on its own. A stage
that came and went before the item existed is not sent late: an item added
five days out gets the 3-day reminder, not a stale 14-day one.

Dates are calendar dates (the inbox shows the date part of ``due_at``), so
"today" is the deployment's calendar day in ``Settings.celery_timezone``, the
same clock the beat schedule runs on.
"""

from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.models.obligation import Obligation, ObligationReminder
from app.models.project import Project, ProjectMembership
from app.models.user import User

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "bell": True,
    "email": False,
    "days_before": [14, 3],
    "on_due": True,
    "overdue": True,
    "weekly_summary": False,
    "team_projects": False,
}
MAX_DAYS_BEFORE = 60
MAX_REMINDER_STAGES = 4
# Items already this far past due when reminders first see them (old
# deadlines, or reminders switched on for the first time) go into one bell
# entry per user rather than one each.
OLD_OVERDUE_DAYS = 30
WEEKLY_SUMMARY = "weekly-summary"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def normalize_settings(raw: dict | None) -> dict[str, Any]:
    """*raw* with every key present and every value of the right type."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_SETTINGS)
    for key in ("bell", "email", "on_due", "overdue", "weekly_summary", "team_projects"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    days = raw.get("days_before")
    if isinstance(days, list):
        clean = sorted(
            {d for d in days if isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= MAX_DAYS_BEFORE},
            reverse=True,
        )
        out["days_before"] = clean[:MAX_REMINDER_STAGES]
    return out


def apply_update(current: dict | None, body: dict) -> dict[str, Any]:
    """Merge a settings update; raises ValueError naming what was wrong."""
    merged = dict(normalize_settings(current))
    for key, value in body.items():
        if key == "days_before":
            if not isinstance(value, list) or any(
                not isinstance(d, int) or isinstance(d, bool) or not 1 <= d <= MAX_DAYS_BEFORE for d in value
            ):
                raise ValueError(f"days_before must be whole numbers of days from 1 to {MAX_DAYS_BEFORE}")
            if len(set(value)) > MAX_REMINDER_STAGES:
                raise ValueError(f"choose at most {MAX_REMINDER_STAGES} reminder days")
            merged["days_before"] = sorted(set(value), reverse=True)
        elif key in DEFAULT_SETTINGS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            merged[key] = value
        else:
            raise ValueError(f"unknown setting {key!r}")
    return merged


# ---------------------------------------------------------------------------
# Dates and stages
# ---------------------------------------------------------------------------

def today_local(settings: Settings | None = None) -> datetime.date:
    tz = ZoneInfo((settings or Settings()).celery_timezone)
    return datetime.datetime.now(tz).date()


def due_date(ob: Obligation) -> datetime.date | None:
    """The calendar date the inbox shows for *ob*."""
    return ob.due_at.date() if ob.due_at else None


def stage_for(days_until: int, prefs: dict[str, Any]) -> str | None:
    """The reminder stage a deadline *days_until* away is in, if any.

    Before the due date it is the nearest configured threshold not yet
    passed: with [14, 3], 10 days out is ``before_14`` and 2 days out is
    ``before_3``. Each stage is sent once, so moving through the window sends
    each reminder once and a late-added item gets only the current one.
    """
    if days_until < 0:
        return "overdue" if prefs["overdue"] else None
    if days_until == 0:
        return "due" if prefs["on_due"] else None
    within = [d for d in prefs["days_before"] if days_until <= d]
    return f"before_{min(within)}" if within else None


def _date_label(day: datetime.date) -> str:
    return f"{day.strftime('%b')} {day.day}, {day.year}"


def _when(days_until: int) -> str:
    if days_until == 0:
        return "today"
    if days_until < 0:
        n = -days_until
        return f"{n} day{'s' if n != 1 else ''} past due"
    return f"in {days_until} day{'s' if days_until != 1 else ''}"


def _source_line(ob: Obligation) -> str:
    if not ob.sources:
        return ""
    s = ob.sources[0]
    page = f", p. {s.page}" if s.page else ""
    return f"Source: {s.document_title or 'document'}{page}."


def deadline_link(ob: Obligation) -> str:
    """The app route that opens Home on this item and its source passage."""
    return f"/?deadline={ob.uuid}"


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------

async def _team_admin_ids(team_id: str) -> set[str]:
    from beanie import PydanticObjectId

    from app.models.team import Team, TeamMembership

    team = await Team.find_one(Team.uuid == team_id)
    if team is None:
        try:
            team = await Team.get(PydanticObjectId(team_id))
        except Exception:
            team = None
    if team is None:
        return set()
    members = await TeamMembership.find(
        {"team": team.id, "role": {"$in": ["owner", "admin"]}},
    ).to_list()
    return {m.user_id for m in members} | {team.owner_user_id}


async def recipients(project: Project) -> list[tuple[User, dict[str, Any]]]:
    """Users reminded about *project*'s deadlines, with their settings."""
    ids = {project.owner_user_id}
    ids |= {m.user_id for m in await ProjectMembership.find(ProjectMembership.project_uuid == project.uuid).to_list()}
    team_admins = await _team_admin_ids(project.team_id) if project.team_id else set()
    users = await User.find({"user_id": {"$in": list(ids | team_admins)}}).to_list()
    out = []
    for user in users:
        prefs = normalize_settings(user.deadline_reminders)
        if user.user_id not in ids and not prefs["team_projects"]:
            continue
        out.append((user, prefs))
    return out


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

@dataclass
class _Due:
    ob: Obligation
    project: Project
    day: datetime.date
    days_until: int
    stage: str


@dataclass
class _Outbox:
    user: User
    prefs: dict[str, Any]
    items: list[_Due] = field(default_factory=list)


async def _claim(ob_uuid: str, user_id: str, stage: str, day: str, channels: list[str]) -> bool:
    """Record a reminder as sent; False if it already was."""
    try:
        await ObligationReminder(
            obligation_uuid=ob_uuid, user_id=user_id, stage=stage, due_date=day, channels=channels,
        ).insert()
    except DuplicateKeyError:
        return False
    return True


async def _open_deadlines(projects: Iterable[str] | None = None) -> list[Obligation]:
    query: dict[str, Any] = {"kind": "deadline", "status": "open", "due_at": {"$ne": None}}
    if projects is not None:
        query["project_uuid"] = {"$in": list(projects)}
    return await Obligation.find(query).to_list()


async def send_due_reminders(today: datetime.date | None = None) -> dict[str, int]:
    """Send every reminder that is due now. Idempotent; run it hourly."""
    from app.services.notification_service import create_notification

    today = today or today_local()
    obligations = await _open_deadlines()
    projects = {
        p.uuid: p for p in await Project.find(
            {"uuid": {"$in": list({o.project_uuid for o in obligations})}, "state": {"$ne": "archived"}},
        ).to_list()
    }
    people: dict[str, list[tuple[User, dict[str, Any]]]] = {}
    outboxes: dict[str, _Outbox] = {}
    counts = {"bell": 0, "email": 0, "bundled": 0}

    for ob in obligations:
        project = projects.get(ob.project_uuid)
        day = due_date(ob)
        if project is None or day is None:
            continue
        if project.uuid not in people:
            people[project.uuid] = await recipients(project)
        days_until = (day - today).days
        for user, prefs in people[project.uuid]:
            if user.user_id in (ob.dismissed_by or []):
                continue
            if not (prefs["bell"] or prefs["email"]):
                continue
            stage = stage_for(days_until, prefs)
            if stage is None:
                continue
            channels = [c for c in ("bell", "email") if prefs[c]]
            if not await _claim(ob.uuid, user.user_id, stage, day.isoformat(), channels):
                continue
            box = outboxes.setdefault(user.user_id, _Outbox(user, prefs))
            box.items.append(_Due(ob, project, day, days_until, stage))

    for box in outboxes.values():
        if box.prefs["bell"]:
            old = [d for d in box.items if d.stage == "overdue" and d.days_until < -OLD_OVERDUE_DAYS]
            for item in box.items:
                if item in old and len(old) > 1:
                    continue
                await create_notification(**_notification(box.user.user_id, item))
                counts["bell"] += 1
            if len(old) > 1:
                await create_notification(
                    user_id=box.user.user_id,
                    kind="deadline_overdue",
                    title=f"{len(old)} older deadlines are past due",
                    body=(
                        "These were past due before reminders reached them and aren't marked "
                        "done: " + "; ".join(f"{d.ob.title} ({d.project.title})" for d in old[:5])
                        + ("…" if len(old) > 5 else "") + ". Mark them done or dismiss them on Home."
                    ),
                    link="/",
                    severity="warning",
                )
                counts["bundled"] += len(old)
        if box.prefs["email"]:
            if await _email_reminders(box):
                counts["email"] += 1
    if any(counts.values()):
        logger.info("Deadline reminders sent: %s", counts)
    return counts


def _notification(user_id: str, item: _Due) -> dict[str, Any]:
    ob, project = item.ob, item.project
    when = _when(item.days_until)
    if item.stage == "overdue":
        title = f"Past due: {ob.title}"
        lead = f"Was due {_date_label(item.day)} ({when}) and isn't marked done."
    elif item.stage == "due":
        title = f"Due today: {ob.title}"
        lead = f"Due {_date_label(item.day)}."
    else:
        title = f"Due {when}: {ob.title}"
        lead = f"Due {_date_label(item.day)}."
    if ob.due_text:
        lead = lead[:-1] + f", {ob.due_text}."
    body = " ".join(part for part in (f"{project.title}.", lead, _source_line(ob)) if part)
    return {
        "user_id": user_id,
        "kind": "deadline_overdue" if item.stage == "overdue" else "deadline_reminder",
        "title": title,
        "body": body,
        "link": deadline_link(ob),
        "item_kind": "obligation",
        "item_id": ob.uuid,
        "item_name": ob.title,
        "severity": "warning" if item.stage in ("overdue", "due") else "info",
    }


async def _email_reminders(box: _Outbox) -> bool:
    from app.services.email_service import deadline_reminder_email, send_email

    if not box.user.email:
        return False
    settings = Settings()
    rows = [_email_row(d, settings.frontend_url) for d in sorted(box.items, key=lambda d: d.days_until)]
    subject, body = deadline_reminder_email(box.user.name or "", rows, settings.frontend_url)
    return await send_email(box.user.email, subject, body, settings, email_type="deadline_reminder")


def _email_row(item: _Due, frontend_url: str) -> dict[str, str]:
    return {
        "title": item.ob.title,
        "project": item.project.title,
        "when": _when(item.days_until),
        "date": _date_label(item.day) + (f", {item.ob.due_text}" if item.ob.due_text else ""),
        "source": _source_line(item.ob),
        "url": f"{frontend_url}{deadline_link(item.ob)}",
    }


async def send_weekly_summaries(today: datetime.date | None = None) -> int:
    """Email each opted-in user what is due this week, next 30 days and overdue."""
    from app.services.email_service import deadline_summary_email, send_email
    from app.services.obligation_service import inbox_projects

    today = today or today_local()
    year, week, _ = today.isocalendar()
    stage = f"{year}-W{week:02d}"
    settings = Settings()
    sent = 0
    for user in await User.find({"deadline_reminders.weekly_summary": True}).to_list():
        if not user.email:
            continue
        projects = await inbox_projects(user)
        groups = upcoming_groups(
            [o for o in await _open_deadlines(projects) if user.user_id not in (o.dismissed_by or [])],
            projects, today,
        )
        if not any(groups[g] for g in ("overdue", "this_week", "next_30_days")):
            continue
        if not await _claim(WEEKLY_SUMMARY, user.user_id, stage, "", ["email"]):
            continue
        rendered = {
            g: [_email_row(d, settings.frontend_url) for d in groups[g]]
            for g in ("overdue", "this_week", "next_30_days")
        }
        subject, body = deadline_summary_email(user.name or "", rendered, settings.frontend_url)
        if await send_email(user.email, subject, body, settings, email_type="deadline_summary"):
            sent += 1
    return sent


def upcoming_groups(
    obligations: list[Obligation], projects: dict[str, Project], today: datetime.date,
) -> dict[str, list[_Due]]:
    """Open deadlines grouped as overdue / this week / next 30 days / later."""
    groups: dict[str, list[_Due]] = defaultdict(list)
    for ob in obligations:
        day = due_date(ob)
        project = projects.get(ob.project_uuid)
        if day is None or project is None:
            continue
        days = (day - today).days
        group = "overdue" if days < 0 else "this_week" if days <= 6 else "next_30_days" if days <= 30 else "later"
        groups[group].append(_Due(ob, project, day, days, group))
    for items in groups.values():
        items.sort(key=lambda d: d.days_until)
    return groups


# ---------------------------------------------------------------------------
# Calendar files (RFC 5545)
# ---------------------------------------------------------------------------

def _ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Fold a content line at 75 octets, never inside a UTF-8 character."""
    out: list[str] = []
    current = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + rest for rest in out[1:]]


def calendar_file(
    items: list[tuple[Obligation, str]],
    *,
    frontend_url: str,
    alarm_days: list[int],
    name: str = "Vandalizer deadlines",
    now: datetime.datetime | None = None,
) -> str:
    """An iCalendar file with one all-day event per dated deadline.

    All-day because the documents give a date (a time, when stated, is kept
    as written in the description): a timed event would restate a time zone
    the document never gave. One alarm per configured reminder day.
    """
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Vandalizer//RA deadlines//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_text(name)}",
    ]
    for ob, project_title in items:
        day = due_date(ob)
        if ob.kind != "deadline" or day is None:
            continue
        description = [f"Project: {project_title}"]
        if ob.due_text:
            description.append(f"Due: {_date_label(day)}, {ob.due_text}")
        for source in ob.sources:
            page = f", p. {source.page}" if source.page else ""
            description.append(f"Source: {source.document_title}{page}: \u201c{source.quote}\u201d")
        if ob.deadline_calculation:
            description.append(f"Calculated: {ob.deadline_calculation.formula}")
        url = f"{frontend_url}{deadline_link(ob)}"
        description.append(url)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ob.uuid}@vandalizer",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + datetime.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_text(ob.title)}",
            f"DESCRIPTION:{_ics_text(chr(10).join(description))}",
            f"URL:{url}",
            "TRANSP:TRANSPARENT",
        ]
        for days in alarm_days:
            lines += [
                "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(ob.title)}",
                f"TRIGGER:-P{days}D", "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
