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
    # Subaward forms label it "Start Date … End Date" or "Project/Award Period".
    "period_of_performance": r"(?:period\s+of\s+performance|performance\s+period|(?:project|award|subaward)\s+period|\bend\s+date\b)",
    "budget_period": r"budget\s+period",
}


_LABEL_PREFIX = r"(?:(?:sub)?award\s+|project\s+|performance\s+|period\s+of\s+performance\s+)?"
_TABLE_LABELS = {
    "start": re.compile(_LABEL_PREFIX + r"(?:start|begin(?:ning)?)\s+date", re.I),
    "end": re.compile(_LABEL_PREFIX + r"end\s+date", re.I),
}
_MD_SEPARATOR = re.compile(r"^[\s|:\-]*-[\s|:\-]*$")


def _split_cells(line: str) -> list[str]:
    """One table row's cells, from Markdown pipes or PyMuPDF's tab-joined rows."""
    if "|" in line:
        line = line.strip()
        line = line[1:] if line.startswith("|") else line
        line = line[:-1] if line.endswith("|") else line
        return [c.strip() for c in line.split("|")]
    return [c.strip() for c in line.split("\t")]


def _table_rows(text: str) -> list[list[str]] | None:
    """The quote as rows of cells, or None when it isn't laid out as a table.

    Covers the layouts the document readers produce: HTML cells (OCR/Docling),
    Markdown pipe tables (pdf-inspector) and tab-joined rows (PyMuPDF). A
    quote may start or end mid-row; the caller checks column alignment.
    """
    from app.services.obligation_service import plain_quote

    if re.search(r"</?t[dh]\b", text, re.I):
        rows = []
        for chunk in re.split(r"</?tr\b[^>]*>", text, flags=re.I):
            pieces = re.split(r"<t[dh]\b[^>]*>", chunk, flags=re.I)
            # Text before the first opening tag is a cell only when the
            # quote starts mid-cell ("End Date</td><td>Aug 31, 2027").
            head, cells = plain_quote(pieces[0]), pieces[1:]
            row = ([head] if head else []) + [plain_quote(c) for c in cells]
            if any(row):
                rows.append(row)
        return rows
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not any("|" in ln or "\t" in ln for ln in lines):
        return None
    return [_split_cells(ln) for ln in lines if not _MD_SEPARATOR.fullmatch(ln)]


# A duration in brackets after a period date: "July 14, 2028 (18 months)".
# Only a length of time: "(or upon termination)" or "(unless extended)" makes
# the date conditional, so such a cell stays unclear.
_DURATION_REMARK = r"\(\s*\d{1,3}\s*(?:months?|mos?\.?|years?|yrs?\.?|weeks?|days?)\s*\)"
_DATE_REMARK = re.compile(r"\s*" + _DURATION_REMARK + r"\s*$", re.I)


def _as_date(text: str) -> datetime.date:
    from app.services.obligation_service import _dates_in

    year, month, day = next(iter(_dates_in(text)))
    if year is None:
        raise ValueError("period dates must include their years")
    return datetime.date(year, month, day)


def _cell_date(cell: str) -> datetime.date | None:
    """The date a cell holds, alone or with a bracketed remark after it.

    Support ticket: an End Date cell reading "July 14, 2028 (18 months)" was
    not read as a date, so every deadline counted from it was refused. Only a
    bracketed duration may follow the date: "Aug 31, 2027 or upon
    termination" and "Aug 31, 2027 (unless extended)" are not plain End Dates.
    """
    from app.services.obligation_service import _DATE_IN_TEXT

    text = cell.strip().rstrip(".")
    if remark := _DATE_REMARK.search(text):
        text = text[:remark.start()].rstrip().rstrip(".")
    match = _DATE_IN_TEXT.fullmatch(text)
    return _as_date(match.group()) if match else None


# Words that make a cell a value or a condition rather than a column label,
# or a label whose own value could be the merged row's date ("Signature Date").
_NOT_A_LABEL = re.compile(
    r"\b(?:upon|until|unless|termination|terminated|completion|completed|pending|tbd|tba|n/?a|none"
    r"|see|signed|executed|due|extended|whichever|after|before|or|dated?|period|term)\b", re.I,
)


def _column_label(cell: str) -> bool:
    """Whether a cell reads as a column label ("Federal Funds Obligated")."""
    words = cell.split()
    return (
        2 <= len(words) <= 6
        and not re.search(r"[\d$%()]", cell)
        and not _NOT_A_LABEL.search(cell)
        and all(w[0].isupper() or w.lower() in {"of", "and", "to", "the", "for", "&"} for w in words)
    )


def _merged_row_date(cells: list[str]) -> datetime.date | None:
    """The End/Start Date of a row whose labels and values were merged.

    Support ticket: the stored text of a NIFA subaward ran two table rows
    together, "End Date|Federal Funds Obligated|August 31, 2027 (18 months)
    $95,550", so the cell beside End Date was another column label. Read only
    that layout: exactly a label cell, then a cell that starts with the date,
    optionally followed by a bracketed duration and a dollar amount (the other
    label's value). A value beside the label ("Upon termination", "TBD") or
    words before the date ("Invoice due Sep 30, 2027") stay unresolved.
    """
    from app.services.obligation_service import _DATE_IN_TEXT

    cells = [c for c in cells if c]
    if len(cells) != 2 or not _column_label(cells[0]):
        return None
    m = re.fullmatch(
        r"(?P<date>" + _DATE_IN_TEXT.pattern + r")\.?(?:\s*" + _DURATION_REMARK + r")?"
        r"(?:\s+\$\s?\d[\d,]*(?:\.\d{2})?)?",
        cells[1].strip(), re.I,
    )
    return _as_date(m["date"]) if m else None


def _labeled_dates(rows: list[list[str]], label: re.Pattern) -> set[datetime.date]:
    """Dates a table gives for *label*: in the label's own cell ("End Date:
    Aug 31, 2027"), in the next cell of its row, or in its column below."""
    found: set[datetime.date] = set()
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            m = re.fullmatch(r"(?:" + label.pattern + r")\s*:?\s*(?P<rest>.*)", cell, re.I | re.S)
            if not m:
                continue
            if m["rest"]:
                if (own := _cell_date(m["rest"])):
                    found.add(own)
                continue
            beside = next((x for x in row[c + 1:] if x), None)
            if beside is not None and (value := _cell_date(beside)):
                found.add(value)
                continue
            # Header row: the value sits in the same column below. Only when
            # the rows line up, so a quote cut mid-row can't shift a column.
            below = rows[r + 1:]
            if below and all(len(b) == len(row) for b in below):
                column = {d for b in below if (d := _cell_date(b[c]))}
                if column:
                    found.update(column)
                    continue
            if (merged := _merged_row_date(row[c + 1:])) is not None:
                found.add(merged)
    return found


def _stacked_dates(text: str) -> dict[str, datetime.date] | None:
    """PyMuPDF's one-cell-per-line table: "Start Date / End Date" headers,
    then their values in the same order."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i in range(len(lines)):
        labels: list[str] = []
        for ln in lines[i:]:
            kind = next((k for k, p in _TABLE_LABELS.items() if p.fullmatch(ln.rstrip(":"))), None)
            if kind is None or kind in labels:
                break
            labels.append(kind)
        if len(labels) < 2:
            continue
        values = lines[i + len(labels): i + 2 * len(labels)]
        dates = [_cell_date(v) for v in values]
        if len(dates) == len(labels) and all(dates):
            return {kind: d for kind, d in zip(labels, dates) if d is not None}
    return None


def _table_period(text: str) -> tuple[datetime.date | None, datetime.date] | None:
    """Start and End Date read from a table, or None when the quote isn't one.

    Support ticket: a NIFA subaward gave "Start Date | End Date" in a page-1
    table, and every deadline anchored on the End Date was refused.
    """
    rows = _table_rows(text)
    if rows is not None:
        found = {kind: _labeled_dates(rows, label) for kind, label in _TABLE_LABELS.items()}
    elif (stacked := _stacked_dates(text)) is not None:
        found = {kind: {stacked[kind]} if kind in stacked else set() for kind in _TABLE_LABELS}
    else:
        return None
    if not found["end"]:
        if found["start"]:
            raise ValueError("the period quote gives a Start Date but no End Date; include the End Date cell")
        return None
    if len(found["end"]) > 1 or len(found["start"]) > 1:
        raise ValueError("the table gives more than one Start or End Date; cite the row for this period only")
    start = next(iter(found["start"]), None)
    end = next(iter(found["end"]))
    if start and start > end:
        raise ValueError("the quoted period start must precede its end")
    return start, end


def _period(source: ObligationSource, role: str) -> tuple[datetime.date | None, datetime.date]:
    from app.services.obligation_service import _DATE_IN_TEXT, _dates_in, _times_in

    text = source.quote
    if not re.search(_PERIOD_NAMES[role], text, re.I):
        raise ValueError(f"the {role} quote must identify that period explicitly")
    if _times_in(text):
        raise ValueError("period anchors with a time of day need clarification before calendar-date calculation")
    table = _table_period(text)
    if table is not None:
        return table
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
    if not re.fullmatch(r"\s*[,;]?\s*(?:[-–—]|through|to|until|(?:and\s+)?end(?:s|ing)?(?:\s+date)?\s*(?:on|is|:)?)\s*", between, re.I):
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
    # A rule copied from a reporting table keeps its cell markup; read it as words.
    from app.services.obligation_service import plain_quote

    rule = plain_quote(timing[0].quote.replace("|", " "))
    if re.search(r"\b(business|working|holiday|weekend|unless|except)\b", rule, re.I) or _times_in(rule):
        raise ValueError("this calculator supports calendar-day rules without time-of-day or business-day exceptions; clarify this rule before adding it")
    offsets = list(_OFFSET.finditer(rule))
    if len(offsets) != 1:
        raise ValueError("cite one relative timing rule with a numeric calendar-day offset")
    match = offsets[0]
    days = int(match['days'])
    direction = match['direction'].lower()
    tail = rule[match.end():].strip().rstrip('.;')
    offset = -days if direction == "before" else days

    # "60 days after March 1, 2027": the rule states its own anchor date, so
    # no period quote is needed (support ticket: a NIFA subaward's annual
    # report was refused as "needs clearer source evidence").
    from app.services.obligation_service import _DATE_IN_TEXT
    stated = _DATE_IN_TEXT.fullmatch(re.sub(r"^(?:the\s+)?", "", tail))
    if stated:
        year, month, day = next(iter(_dates_in(stated.group())))
        if year is None:
            raise ValueError("a stated anchor date must include its year")
        if direction == "of":
            raise ValueError("the rule must say before or after its anchor date")
        anchor = datetime.date(year, month, day)
        return [_occurrence(rule, "stated_date", anchor, offset)]

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
    elif re.fullmatch(
        r"(?:the\s+)?end\s+of\s+(?:the\s+)?(?:period\s+of\s+performance|performance\s+period)"
        # "120 days after the End Date": the subaward's end, i.e. the quoted period's end.
        r"|(?:the\s+)?(?:(?:sub)?award\s+|project\s+)?(?:end|expiration|completion)\s+date(?:\s+of\s+(?:this|the)\s+(?:sub)?award)?",
        tail, re.I,
    ):
        if direction == "of":
            raise ValueError("the rule must specify before or after the performance-period end")
        anchors = [end]
        anchor_kind = "performance_period_end"
    elif re.fullmatch(
        # "within 30 days after the Start Date". Support ticket: deadlines
        # counted from a subaward table's Start Date were all refused.
        # Not "the Effective Date": a subaward's effective date often differs
        # from its start date and no source states it, so it stays refused.
        r"(?:the\s+)?(?:(?:start|beginning)\s+of\s+(?:the\s+)?(?:period\s+of\s+performance|performance\s+period)"
        r"|(?:(?:sub)?award\s+|project\s+)?(?:start|begin(?:ning)?)\s+date(?:\s+of\s+(?:this|the)\s+(?:sub)?award)?)",
        tail, re.I,
    ):
        if direction == "of":
            raise ValueError("the rule must specify before or after the performance-period start")
        if start is None:
            raise ValueError("the period quote must give the Start Date this rule counts from")
        anchors = [start]
        anchor_kind = "performance_period_start"
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
    return [_occurrence(rule, anchor_kind, anchor, offset) for anchor in anchors]


def _occurrence(rule: str, anchor_kind: str, anchor: datetime.date, offset: int) -> dict:
    due = anchor + datetime.timedelta(days=offset)
    calculation = DeadlineCalculation(
        rule=rule, anchor_kind=anchor_kind, anchor_date=anchor.isoformat(), offset_days=offset,
        formula=f"{anchor.isoformat()} {'−' if offset < 0 else '+'} {abs(offset)} calendar days = {due.isoformat()}",
    )
    return {"due_at": datetime.datetime.combine(due, datetime.time()), "due_text": None, "deadline_calculation": calculation}
