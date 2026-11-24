"""Check a Page's figures against the files it was built from.

Support ticket: Pages built from documents carry many figures, but nothing
said where any of them came from, whether it was calculated, or whether it
was changed by hand. Saving did not check anything; a page shipped with a
wrong figure and a false source note (#1122) that was found only by checking
every number by hand.

``check`` runs when a Page preview is prepared, against the source files
Living Pages records on the revision (``source.documents``). Every dollar
amount and percentage on the Page is one of:

* **stated**: a source file states it, to the precision the Page shows
  ("$1.25M" for 1,250,000). Its origin names the file and where in it: the
  sheet, row and column of a spreadsheet, or the page of a PDF.
* **calculated**: a sum, difference, ratio or percentage of stated figures in
  the same row or sentence (see ``figure_derivation``), with its formula.
* **manual**: chat marked it as a figure the user changed by hand, with
  ``data-source-value`` holding what the source says. The check confirms the
  source does say that, so a manual edit can't hide an invented figure.
* **unmatched**: none of the above.

The result is stored on the revision. ``annotate`` adds each figure's origin
as hover text when the Page is shown, plus a "Figures checked" line, and the
preview card and Share dialog show the summary. It checks values, not
meaning: a stated figure in the wrong row would still match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup, NavigableString, Tag

from app.services.figure_derivation import Figure, _figures, derive_figures
from app.services.kb_answer_grounding import _MONEY_RE, _PERCENT_RE, bare_amounts_as_money

if TYPE_CHECKING:
    from pymongo.database import Database

MAX_SOURCE_CHARS = 2_000_000
MAX_FIGURES = 400
_BLOCKS = ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "dt", "dd",
           "caption", "figcaption", "section", "article", "header", "footer", "blockquote", "summary")
_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}")
_PLAIN_NUMBER = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")


@dataclass
class _Location:
    title: str
    sheet: str | None = None
    page: int | None = None
    row: str | None = None
    column: str | None = None

    def describe(self) -> str:
        parts = [self.title]
        if self.sheet:
            parts.append(self.sheet)
        where = ", ".join(p for p in (self.row, self.column) if p)
        if where:
            parts.append(where)
        text = " · ".join(parts)
        return f"{text}, p. {self.page}" if self.page else text


@dataclass
class _SourceValue:
    value: float
    percent: bool
    location: _Location


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row_label(cells: list[str]) -> str | None:
    for cell in cells:
        if re.search(r"[A-Za-z]", cell) and not _MONEY_RE.search(cell) and not _PERCENT_RE.search(cell):
            return cell[:60]
    return None


def _index_source(title: str, text: str, markers: list[dict] | None) -> list[_SourceValue]:
    from app.services.extraction_sources import page_for_offset

    values: list[_SourceValue] = []
    sheet: str | None = None
    header: list[str] | None = None
    offset = 0
    for line in text[:MAX_SOURCE_CHARS].split("\n"):
        start = offset
        offset += len(line) + 1
        stripped = line.strip()
        if stripped.startswith("## "):
            sheet = stripped[3:].strip()[:60]
            header = None
            continue
        is_row = stripped.startswith("|")
        if not is_row:
            header = None
        elif _SEPARATOR.match(stripped):
            continue
        cells = _cells(stripped) if is_row else []
        if is_row and header is None:
            header = cells
        page = page_for_offset(start, markers) if markers else None
        row = _row_label(cells) if is_row else None
        for piece_index, piece in enumerate(cells if is_row else [line]):
            column = header[piece_index] if is_row and header and piece_index < len(header) and header is not cells else None
            # A spreadsheet cell holding a plain number is an amount, however
            # small ("0" for an empty year); prose only counts 4+ digit ones.
            cell = piece.strip()
            if is_row and _PLAIN_NUMBER.fullmatch(cell):
                cell = "$" + cell
            for figure in _figures(cell if is_row else bare_amounts_as_money(piece)):
                values.append(_SourceValue(figure.value, figure.percent, _Location(
                    title, sheet, page, row, (column or None) and column[:40],
                )))
    return values


def load_sources(db: Database[dict], documents: list[dict]) -> list[tuple[str, list[_SourceValue]]]:
    """Each recorded source file's title and indexed figures."""
    uuids = [d["uuid"] for d in documents if isinstance(d, dict) and d.get("uuid")]
    if not uuids:
        return []
    found = {
        d["uuid"]: d for d in db.smart_document.find(
            {"uuid": {"$in": uuids}}, {"uuid": 1, "title": 1, "raw_text": 1, "text_markers": 1},
        )
    }
    out = []
    for uuid in uuids:
        doc = found.get(uuid)
        if doc and doc.get("raw_text"):
            title = doc.get("title") or "Untitled file"
            out.append((title, _index_source(title, doc["raw_text"], doc.get("text_markers"))))
    return out


# ---------------------------------------------------------------------------
# The Page
# ---------------------------------------------------------------------------


def _page_text(soup: BeautifulSoup) -> str:
    """Visible text with tables as "| a | b |" rows, so a row's figures share a scope."""
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    for table in soup.find_all("table"):
        lines: list[str] = []
        for i, tr in enumerate(table.find_all("tr")):
            cells = [c.get_text(" ", strip=True).replace("|", "/") for c in tr.find_all(["th", "td"])]
            lines.append("| " + " | ".join(cells) + " |")
            if i == 0:
                lines.append("|" + " --- |" * len(cells))
        table.replace_with(NavigableString("\n" + "\n".join(lines) + "\n"))
    for tag in soup.find_all(_BLOCKS):
        tag.append(NavigableString("\n"))
    return re.sub(r"\n\s*\n+", "\n", soup.get_text())


def _manual_edits(soup: BeautifulSoup) -> list[dict]:
    edits = []
    for tag in soup.find_all(attrs={"data-source-value": True}):
        page_value = tag.get_text(" ", strip=True)
        source_value = str(tag.get("data-source-value") or "").strip()
        if not page_value or not source_value:
            continue
        row = tag.find_parent("tr")
        label = _row_label([c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]) if row else None
        edits.append({"figure": page_value, "source_value": source_value, "where": label})
    return edits


_MAX_ORIGINS = 12


def _matches(figure: Figure, sources: list[tuple[str, list[_SourceValue]]]) -> list[_Location]:
    found: list[_Location] = []
    for _title, values in sources:
        for value in values:
            if value.percent == figure.percent and abs(value.value - figure.value) <= figure.tolerance:
                found.append(value.location)
                if len(found) >= _MAX_ORIGINS:
                    return found
    return found


def _origin(location: _Location) -> dict[str, Any]:
    return {"text": location.describe(), "row": location.row, "column": location.column}


def strip_annotations(soup: BeautifulSoup) -> None:
    """Remove figure-check markup that isn't ours to trust.

    Stored HTML never holds annotations: they are added when a Page is shown.
    Any that are present were written into the page (for example copied from
    a preview chat was shown), so their hover text is stale or invented.
    """
    for element in soup.select("#vandalizer-figure-style, #vandalizer-figure-check"):
        element.decompose()
    for span in soup.find_all(class_=re.compile(r"^vz-figure")):
        if isinstance(span, Tag):
            span.unwrap()


def check(html: str, sources: list[tuple[str, list[_SourceValue]]]) -> dict[str, Any] | None:
    """The figure check for a Page's HTML, or None when it has no source files."""
    if not sources:
        return None
    soup = BeautifulSoup(html or "", "html.parser")
    strip_annotations(soup)
    manual = _manual_edits(soup)
    text = _page_text(soup)
    figures: list[Figure] = []
    seen: set[str] = set()
    for figure in _figures(text):
        if figure.label not in seen:
            seen.add(figure.label)
            figures.append(figure)
    figures = figures[:MAX_FIGURES]

    results: dict[str, dict[str, Any]] = {}
    manual_by_figure = {m["figure"]: m for m in manual}
    known_money: set[float] = set()
    known_pct: set[float] = set()
    for _title, values in sources:
        for v in values:
            (known_pct if v.percent else known_money).add(v.value if v.percent else round(v.value, 2))
    for figure in figures:
        edit = manual_by_figure.get(figure.label)
        if edit:
            source_figures = _figures(edit["source_value"])
            locations = _matches(source_figures[0], sources) if source_figures else []
            results[figure.label] = {
                "figure": figure.label, "status": "manual", "source_value": edit["source_value"],
                "where": edit["where"], "source_value_found": bool(locations),
                "origin": locations[0].describe() if locations else None,
            }
        else:
            locations = _matches(figure, sources)
            if not locations:
                continue
            # The same value can sit in several cells ($15k in Y1 and Y2);
            # the hover picks the one in the row and column it's shown in.
            results[figure.label] = {"figure": figure.label, "status": "stated",
                                     "origin": locations[0].describe(),
                                     "origins": [_origin(loc) for loc in locations]}
        # Stated and manual figures feed calculations (a total after a manual edit).
        (known_pct if figure.percent else known_money).add(figure.value if figure.percent else round(figure.value, 2))

    for derivation in derive_figures(text, known_money, known_pct):
        if derivation.label not in results:
            results[derivation.label] = {"figure": derivation.label, "status": "calculated", "formula": derivation.formula}
    for figure in figures:
        results.setdefault(figure.label, {"figure": figure.label, "status": "unmatched"})

    ordered = [results[f.label] for f in figures]
    counts = {status: sum(1 for r in ordered if r["status"] == status)
              for status in ("stated", "calculated", "manual", "unmatched")}
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": [title for title, _values in sources],
        "total": len(ordered),
        **counts,
        "figures": ordered,
    }


def with_check(db: Database[dict], html: str, title: str, source: dict[str, Any]) -> dict[str, Any]:
    """``source`` plus the figure check of ``html`` against its recorded files."""
    from app.services.artifacts import clean_html

    prepared, _warnings = clean_html(html, title)
    result = check(prepared, load_sources(db, source.get("documents") or []))
    return {**source, "figure_check": result} if result is not None else source


def summary(result: dict[str, Any] | None) -> str:
    """One line for the preview card, chat and the Share dialog."""
    if not result:
        return "Figures not checked: this Page has no recorded source file."
    total = result["total"]
    if not total:
        return "No dollar amounts or percentages to check."
    matched = result["stated"] + result["calculated"]
    parts = [f"{matched} of {total} figures match the source"
             + (f" ({result['calculated']} calculated)" if result["calculated"] else "")]
    manual = [f for f in result["figures"] if f["status"] == "manual"]
    if manual:
        names = ", ".join(f"{m['where'] or m['figure']}" for m in manual[:3])
        parts.append(f"{len(manual)} manual edit{'s' if len(manual) != 1 else ''} ({names})")
    unmatched = [f["figure"] for f in result["figures"] if f["status"] == "unmatched"]
    if unmatched:
        parts.append(f"{len(unmatched)} not found in the source ({', '.join(unmatched[:5])}"
                     + (", …" if len(unmatched) > 5 else "") + ")")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Showing it on the Page
# ---------------------------------------------------------------------------

_FIGURE_STYLE = """
.vz-figure{text-decoration:underline dotted;text-underline-offset:2px;cursor:help}
.vz-figure--manual{background:#fef3c7}
.vz-figure--unmatched{text-decoration-color:#b91c1c}
#vandalizer-figure-check{margin:2em 0 0;padding:.6em .8em;border-top:1px solid #d1d5db;font:12px/1.5 system-ui,sans-serif;color:#4b5563}
@media print{.vz-figure{text-decoration:none}}
"""


def note(result: dict[str, Any], public: bool = False) -> str:
    when = result.get("checked_at") or ""
    try:
        when = datetime.fromisoformat(when).strftime("%b %-d, %Y")
    except ValueError:
        pass
    # A public link keeps file names private (as its source details are).
    sources = "the source files" if public else ", ".join(result.get("sources") or []) or "the source files"
    return f"Figures checked against {sources} on {when} · {summary(result)}"


def _cell_position(node: Any) -> tuple[str | None, str | None]:
    """(row label, column header) of the table cell holding *node*, if any."""
    cell = node.find_parent(["td", "th"])
    row = cell.find_parent("tr") if cell else None
    table = row.find_parent("table") if row else None
    if not (cell and row and table):
        return None, None
    cells = row.find_all(["th", "td"])
    label = _row_label([c.get_text(" ", strip=True) for c in cells])
    header_row = table.find("tr")
    column = None
    if header_row is not None and header_row is not row:
        headers = header_row.find_all(["th", "td"])
        index = cells.index(cell)
        if index < len(headers):
            column = headers[index].get_text(" ", strip=True)
    return label, column


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def _hover(entry: dict[str, Any], node: Any = None, public: bool = False) -> str:
    status = entry["status"]
    if public:
        # No file names, cell locations or the source values behind hand edits.
        return {"stated": "Found in the source files", "calculated": "Calculated from figures in the source files",
                "manual": "Edited by hand after the check"}.get(status, "Not found in the source files")
    if status == "stated":
        origins = entry.get("origins") or []
        if node is not None and len(origins) > 1:
            row, column = _cell_position(node)
            best = (next((o for o in origins if _same(o["row"], row) and _same(o["column"], column)), None)
                    or next((o for o in origins if _same(o["row"], row)), None))
            if best:
                return f"From {best['text']}"
        return f"From {entry['origin']}"
    if status == "calculated":
        return f"Calculated: {entry['formula']}"
    if status == "manual":
        found = "" if entry.get("source_value_found") else " (not found in the source)"
        return f"Manual edit: source says {entry['source_value']}{found}"
    return "Not found in the source files"


def annotate(soup: BeautifulSoup, result: dict[str, Any] | None, public: bool = False) -> None:
    """Hover text on each checked figure and a "Figures checked" line, in place."""
    strip_annotations(soup)
    if not result or not soup.body:
        return
    entries = {e["figure"]: e for e in result.get("figures") or []}
    pattern = re.compile(f"{_MONEY_RE.pattern}|{_PERCENT_RE.pattern}", re.IGNORECASE)
    for node in list(soup.body.find_all(string=True)):
        if node.parent is None or node.parent.name in {"script", "style", "title"}:
            continue
        text = str(node)
        pieces: list[Any] = []
        last = 0
        for m in pattern.finditer(text):
            entry = entries.get(m.group(0).strip())
            if not entry:
                continue
            pieces.append(text[last:m.start()])
            span = soup.new_tag("span", attrs={
                "class": f"vz-figure vz-figure--{entry['status']}", "title": _hover(entry, node, public),
            })
            span.string = m.group(0)
            pieces.append(span)
            last = m.end()
        if not pieces:
            continue
        pieces.append(text[last:])
        for piece in pieces:
            node.insert_before(piece if isinstance(piece, Tag) else NavigableString(piece))
        node.extract()
    head = soup.head
    if head is not None:
        style = soup.new_tag("style", id="vandalizer-figure-style")
        style.string = _FIGURE_STYLE
        head.append(style)
    footer = soup.new_tag("aside", id="vandalizer-figure-check", role="note")
    footer.string = note(result, public)
    soup.body.append(footer)
