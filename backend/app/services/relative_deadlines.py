"""Bounded calendar-day schedules from already verified source quotations.

No model-supplied computed dates or inferred budget periods are used. Unsupported
rules stay unresolved for the RA instead of being approximated by the model.
"""

import datetime
import re

from app.models.obligation import DeadlineCalculation, ObligationSource

MAX_OCCURRENCES = 100
_OFFSET = re.compile(r"\b(?P<days>\d{1,3})\s+(?:calendar\s+)?days?\s+(?P<direction>before|after|of)\s+", re.I)
_PERIOD_NAMES = {
    "period_of_performance": r"(?:period\s+of\s+performance|performance\s+period)",
    "budget_period": r"budget\s+period",
}


def _period(source: ObligationSource, role: str) -> tuple[datetime.date | None, datetime.date]:
    from app.services.obligation_service import _DATE_IN_TEXT, _dates_in, _times_in

    text = source.quote
    if not re.search(_PERIOD_NAMES[role], text, re.I):
        raise ValueError(f"the {role} quote must identify that period explicitly")
    if _times_in(text):
        raise ValueError("period anchors with a time of day need clarification before calendar-date calculation")
    matches = list(_DATE_IN_TEXT.finditer(text))
    if len(matches) not in (1, 2):
        raise ValueError(f"cite one {role} per source, with its full start and end dates")
    dates = []
    for match in matches:
        year, month, day = next(iter(_dates_in(match.group())))
        if year is None:
            raise ValueError("period dates must include their years")
        dates.append(datetime.date(year, month, day))
    if len(dates) == 1:
        if not re.search(r"\bend(?:s|ing)?(?:\s+date)?\s*(?:on|is|:)?\s*$", text[:matches[0].start()], re.I):
            raise ValueError("a single period date must be explicitly labeled as its end date")
        return None, dates[0]
    between = text[matches[0].end():matches[1].start()]
    if not re.fullmatch(r"\s*,?\s*(?:[-–—]|through|to|until|(?:and\s+)?end(?:s|ing)?(?:\s+date)?\s*(?:on|is|:)?)\s*", between, re.I):
        raise ValueError("the period quote must explicitly connect its start and end dates, not unrelated dates")
    if dates[0] > dates[1]:
        raise ValueError("the quoted period start must precede its end")
    return dates[0], dates[1]


def calculate_deadlines(sources: list[ObligationSource]) -> list[dict]:
    """Expand one quoted rule into dated occurrences, or raise a useful reason."""
    from app.services.obligation_service import _dates_in, _times_in

    timing = [s for s in sources if s.role == "timing"]
    if len(timing) != 1:
        raise ValueError("relative deadlines need exactly one source with role 'timing'")
    rule = timing[0].quote
    if re.search(r"\b(business|working|holiday|weekend|unless|except)\b", rule, re.I) or _times_in(rule):
        raise ValueError("this calculator supports calendar-day rules without time-of-day or business-day exceptions; clarify this rule before adding it")
    offsets = list(_OFFSET.finditer(rule))
    if len(offsets) != 1:
        raise ValueError("cite one relative timing rule with a numeric calendar-day offset")
    match = offsets[0]
    days = int(match['days'])
    direction = match['direction'].lower()
    tail = rule[match.end():].strip().rstrip('.;')
    performance = [s for s in sources if s.role == "period_of_performance"]
    if len(performance) != 1:
        raise ValueError("cite the Period of Performance dates in one source with role 'period_of_performance'")
    start, end = _period(performance[0], "period_of_performance")
    anchors: list[datetime.date] = []

    if re.fullmatch(r"(?:the\s+)?end\s+of\s+(?:(?:each|the|a)\s+)?budget\s+period", tail, re.I):
        if direction == "of":
            raise ValueError("the rule must specify before or after the budget-period end")
        periods = [s for s in sources if s.role == "budget_period"]
        if not periods:
            raise ValueError("cite the dates of each budget period with role 'budget_period'; do not infer them from the Period of Performance")
        for source in periods:
            budget_start, budget_end = _period(source, "budget_period")
            if budget_end > end or (start and (budget_start or budget_end) < start):
                raise ValueError("the cited budget period falls outside the Period of Performance")
            anchors.append(budget_end)
        anchor_kind = "budget_period_end"
    elif re.fullmatch(r"(?:the\s+)?end\s+of\s+(?:the\s+)?(?:period\s+of\s+performance|performance\s+period)", tail, re.I):
        if direction == "of":
            raise ValueError("the rule must specify before or after the performance-period end")
        anchors = [end]
        anchor_kind = "performance_period_end"
    else:
        # Fixed annual dates are bounded by the quoted performance period.
        # Require the entire tail to be dates and separators, not an unparsed
        # qualifier such as 'whichever is earlier'.
        from app.services.obligation_service import _DATE_IN_TEXT

        if not re.match(r"each\s+", tail, re.I):
            raise ValueError("unsupported relative anchor; cite a period-end rule or 'each' followed by annual dates")
        date_text = re.sub(r"^each\s+", "", tail, flags=re.I)
        remainder = _DATE_IN_TEXT.sub("", date_text)
        if re.sub(r"\band\b|\beach\b|[\s,]", "", remainder, flags=re.I):
            raise ValueError("the recurring rule contains an unsupported qualifier; clarify it before adding dates")
        dates = _dates_in(date_text)
        if not dates or any(year is not None for year, _month, _day in dates):
            raise ValueError("annual recurrence needs month/day anchors without a year")
        if start is None:
            raise ValueError("annual recurrence needs the full Period of Performance start and end dates")
        if end.year - start.year > 50:
            raise ValueError("the recurrence spans too many years; review a narrower period")
        for year in range(start.year, end.year + 1):
            for _year, month, day in sorted(dates):
                anchor = datetime.date(year, month, day)
                if start <= anchor <= end:
                    anchors.append(anchor)
        anchor_kind = "annual_date"

    anchors = sorted(set(anchors))
    if not anchors:
        raise ValueError("no reporting anchors fall within the quoted performance period")
    if len(anchors) > MAX_OCCURRENCES:
        raise ValueError("too many occurrences; review a narrower period")
    offset = -days if direction == "before" else days
    results = []
    for anchor in anchors:
        due = anchor + datetime.timedelta(days=offset)
        calculation = DeadlineCalculation(
            rule=rule, anchor_kind=anchor_kind, anchor_date=anchor.isoformat(), offset_days=offset,
            formula=f"{anchor.isoformat()} {'−' if offset < 0 else '+'} {abs(offset)} calendar days = {due.isoformat()}",
        )
        results.append({"due_at": datetime.datetime.combine(due, datetime.time()),
                        "due_text": None, "deadline_calculation": calculation})
    return results
