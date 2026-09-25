"""Schedule-trigger configuration: plain daily/weekly/monthly picks, in a zone.

A schedule automation's ``trigger_config`` carries what the user picked —

* ``frequency``: ``"daily" | "weekly" | "monthly"``
* ``time``: ``"HH:MM"`` (24-hour), in ``timezone``
* ``weekday``: 0 (Monday) … 6 (Sunday), weekly only
* ``day_of_month``: 1 … 28, monthly only — every month has one
* ``timezone``: an IANA name (``"America/Boise"``); ``"UTC"`` when omitted

— and ``cron_expression`` is derived from those here, never typed. A config
with no ``frequency`` but its own ``cron_expression`` (API-created before the
picker existed) keeps working as written.

Every "when is the next run" answer — the scheduler's, the wizard preview's,
and the one on the automation — comes from ``next_runs`` so they cannot
disagree. Times are evaluated in the schedule's zone, so 9:00 stays 9:00
across a daylight-saving change.
"""

from __future__ import annotations

import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

FREQUENCIES = ("daily", "weekly", "monthly")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown time zone: {name!r}")


def build_cron(cfg: dict) -> str:
    """The cron expression for a picker config. Raises ValueError naming the bad field."""
    frequency = cfg.get("frequency")
    if frequency not in FREQUENCIES:
        raise ValueError("Schedule frequency must be daily, weekly or monthly")
    match = _TIME_RE.match(str(cfg.get("time") or ""))
    if not match:
        raise ValueError("Schedule time must be HH:MM (24-hour)")
    hour, minute = int(match.group(1)), int(match.group(2))
    if frequency == "daily":
        return f"{minute} {hour} * * *"
    if frequency == "weekly":
        weekday = cfg.get("weekday")
        if not isinstance(weekday, int) or not 0 <= weekday <= 6:
            raise ValueError("Weekly schedules need a weekday (0 = Monday … 6 = Sunday)")
        # cron counts Sunday as 0; the config counts Monday as 0.
        return f"{minute} {hour} * * {(weekday + 1) % 7}"
    day = cfg.get("day_of_month")
    if not isinstance(day, int) or not 1 <= day <= 28:
        raise ValueError("Monthly schedules need a day of the month from 1 to 28")
    return f"{minute} {hour} {day} * *"


def normalize_schedule_config(cfg: dict | None) -> dict:
    """Validate a schedule ``trigger_config`` and fill in ``cron_expression``.

    Returns a new dict. Raises ValueError with a message fit for a 422.
    """
    out = dict(cfg or {})
    if out.get("frequency"):
        out["cron_expression"] = build_cron(out)
    elif not out.get("cron_expression"):
        raise ValueError("Schedule trigger requires a frequency and time")
    if not croniter.is_valid(out["cron_expression"]):
        raise ValueError(f"Invalid cron expression: {out['cron_expression']!r}")
    out["timezone"] = str(_zone(out.get("timezone")))
    if out.get("source") not in (None, "folder", "documents"):
        raise ValueError("Schedule source must be 'folder' or 'documents'")
    out["only_new"] = bool(out.get("only_new"))
    return out


def next_runs(cfg: dict, after: datetime.datetime, count: int = 1) -> list[datetime.datetime]:
    """The next ``count`` run times strictly after ``after``, as UTC datetimes."""
    if after.tzinfo is None:
        after = after.replace(tzinfo=datetime.timezone.utc)
    zone = _zone(cfg.get("timezone"))
    # Iterate on the zone's wall clock and attach the zone afterwards:
    # croniter stepping an aware zoneinfo datetime across a DST change lands
    # an hour off (9:00 became 10:00 the day after the clocks fell back).
    it = croniter(cfg["cron_expression"], after.astimezone(zone).replace(tzinfo=None))
    runs: list[datetime.datetime] = []
    while len(runs) < count:
        local = it.get_next(datetime.datetime).replace(tzinfo=zone)
        run = local.astimezone(datetime.timezone.utc)
        if run > after:
            runs.append(run)
    return runs


def last_run_base(auto: dict | object, fallback: datetime.datetime) -> datetime.datetime:
    """The point the next run is counted from, as an aware UTC datetime: the
    latest of when the schedule last fired, when it was created, and when it
    was last enabled or changed (``schedule_armed_at``). The last keeps a
    paused schedule from firing the slot it missed the moment it is switched
    back on, and a changed time from firing a slot that no longer applies.
    """
    get = auto.get if isinstance(auto, dict) else lambda k, d=None: getattr(auto, k, d)
    stamps = [
        s for s in (get("last_scheduled_run_at"), get("schedule_armed_at"), get("created_at"))
        if s is not None
    ]
    if not stamps:
        stamps = [fallback]
    aware = [s if s.tzinfo else s.replace(tzinfo=datetime.timezone.utc) for s in stamps]
    return max(aware)
