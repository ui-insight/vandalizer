"""Fresh calendar context from the server clock, in the caller's local zone."""
from calendar import monthrange
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def current_date_context(client_timezone: str | None = None, *, now: datetime | None = None) -> str:
    fallback = False
    try:
        zone = ZoneInfo(client_timezone or "UTC")
        fallback = not client_timezone
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
        fallback = True
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local = instant.astimezone(zone)
    first = local.date().replace(day=1)
    last = first.replace(day=monthrange(local.year, local.month)[1])
    return (
        "CURRENT DATE AND TIME (runtime clock for this turn)\n"
        f"Time zone: {zone.key}"
        + (" (UTC fallback: the user's local timezone was not available)." if fallback else ".")
        + f"\nToday: {local.date().isoformat()} ({local:%A, %B} {local.day}, {local.year})."
        + f"\nCurrent local time: {local.isoformat(timespec='seconds')}."
        + f"\nThis month: {first.isoformat()} through {last.isoformat()}, inclusive.\n"
        "Use this current date for today, now, relative deadlines, and this month unless the user "
        "explicitly requests another reference date or timezone. Previous messages and document dates "
        "do not define today's date. These runtime facts do not require document evidence. "
        "Answer date questions directly; do not say you lack the current date or ask the user to supply it. "
        "When asked to add today's date to a Page, write the actual date in the HTML (for example, "
        f"Updated: {local:%B} {local.day}, {local.year}), never a [today's date] placeholder. "
        "Do not tell the user to edit HTML to supply a date already provided here. "
        "Calculate days until a deadline from local calendar dates. For award status or due-date questions, "
        "still read the relevant records: the clock supplies the reference date, not missing award terms, "
        "amendments, deadlines, or completion status."
    )
