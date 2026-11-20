"""What changed between two saved versions of a Page.

Support ticket: a budget Page revised five times (rebudgets, corrections)
could only be viewed one version at a time, and chat said it couldn't read
older versions. For a revised budget the change is often the information.

A Page is static HTML, so the comparison reads it as a person would:

* **Numbers.** Table cells are matched by section, row label and column
  header ("Equipment · Y2: $15,000 → $20,000"). Elsewhere, blocks are diffed
  in order; when only the numbers in a block changed, each one is reported
  with the block's label, or the line before it for a lone KPI value.
* **Sections** added or removed, by heading.
* **Text** other edits, as before → after snippets.
* **Design** CSS and style-only changes (colours, fonts) grouped on their own,
  so a re-theme doesn't bury a changed figure.

Everything is derived from the two stored revisions; nothing is guessed.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

from bs4 import BeautifulSoup, Tag

MAX_ITEMS = 60
_SNIPPET = 140
_NUMBER = re.compile(r"[-−]?[$€£]?\d[\d,]*(?:\.\d+)?\s?(?:%|[kKmMbB]\b|million\b|billion\b)?")
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BLOCKS = ("p", "li", "dt", "dd", "figcaption", "caption", "summary", "blockquote", "pre", "address", "time", *_HEADINGS)
_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
_SPACE = re.compile(r"\s+")


def _text(node: Tag) -> str:
    return _SPACE.sub(" ", node.get_text(" ", strip=True)).strip()


def _clip(text: str) -> str:
    return text if len(text) <= _SNIPPET else text[: _SNIPPET - 1].rstrip() + "…"


def _skeleton(text: str) -> str:
    return _NUMBER.sub("#", text)


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _section_of(node: Tag) -> str:
    heading = node.find_previous(_HEADINGS)
    return _text(heading) if isinstance(heading, Tag) else ""


def _tables(soup: BeautifulSoup) -> dict[tuple[str, ...], str]:
    """(section, table#, row label, column header) → cell text."""
    cells: dict[tuple[str, ...], str] = {}
    per_section: Counter[str] = Counter()
    for table in soup.find_all("table"):
        if not isinstance(table, Tag) or table.find_parent("table"):
            continue
        section = _section_of(table)
        per_section[section] += 1
        index = str(per_section[section])
        rows = [r for r in table.find_all("tr") if isinstance(r, Tag) and r.find_parent("table") is table]
        if not rows:
            continue
        header = [_text(c) for c in rows[0].find_all(["th", "td"])]
        seen: Counter[str] = Counter()
        for row in rows[1:]:
            values = [_text(c) for c in row.find_all(["th", "td"])]
            if not values:
                continue
            label = next((v for v in values if v), "")
            seen[label] += 1
            row_key = label if seen[label] == 1 else f"{label} ({seen[label]})"
            for i, value in enumerate(values):
                if i == 0:
                    continue
                column = header[i] if i < len(header) and header[i] else f"column {i + 1}"
                cells[(section, index, row_key, column)] = value
    return cells


def _blocks(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(kind, text) for every leaf text block outside tables, in page order."""
    out: list[tuple[str, str]] = []
    body = soup.body or soup
    for node in body.find_all(True):
        if not isinstance(node, Tag) or node.name in ("table", "style", "script", "title", "head") or node.find_parent("table"):
            continue
        is_block = node.name in _BLOCKS
        # A div/span with only text (a KPI label or value) counts as a block.
        is_leaf = node.name in ("div", "span", "strong", "b", "small", "em") and not node.find(True)
        if not (is_block or is_leaf):
            continue
        if node.find_parent(_BLOCKS):
            continue
        text = _text(node)
        if text:
            out.append(("heading" if node.name in _HEADINGS else "block", text))
    return out


def _styles(soup: BeautifulSoup) -> tuple[str, list[str]]:
    css = "\n".join(s.get_text() for s in soup.find_all("style"))
    inline = [str(t.get("style")) for t in soup.find_all(True) if isinstance(t, Tag) and t.get("style")]
    inline += [" ".join(t.get("class") or []) for t in soup.find_all(True) if isinstance(t, Tag) and t.get("class")]
    return css, inline


def _number_changes(label: str, old: str, new: str) -> list[dict]:
    old_numbers, new_numbers = _NUMBER.findall(old), _NUMBER.findall(new)
    if len(old_numbers) != len(new_numbers):
        return []
    changes = []
    for i, (a, b) in enumerate(zip(old_numbers, new_numbers)):
        if a.strip() == b.strip():
            continue
        # Label each figure with the words just before it in the block.
        prefix = _NUMBER.split(new)[i].strip(" :–—-|·,")
        name = prefix[-60:].strip() if prefix else ""
        changes.append({"label": " · ".join(p for p in (label, name) if p) or "Figure",
                        "old": a.strip(), "new": b.strip()})
    return changes


def compare(old_html: str, new_html: str) -> dict[str, Any]:
    """The differences between two Page HTML revisions, grouped for people."""
    old, new = _parse(old_html), _parse(new_html)
    numbers: list[dict] = []
    text: list[dict] = []

    # Tables, cell by cell.
    old_cells, new_cells = _tables(old), _tables(new)
    rows_added = {k[:3] for k in new_cells} - {k[:3] for k in old_cells}
    rows_removed = {k[:3] for k in old_cells} - {k[:3] for k in new_cells}
    for key, value in new_cells.items():
        before = old_cells.get(key)
        if before is None or before == value:
            continue
        section, _, row, column = key
        label = " · ".join(p for p in (row, column) if p)
        if _skeleton(before) == _skeleton(value) and _NUMBER.search(value):
            numbers.append({"label": label, "old": before, "new": value, "section": section})
        else:
            text.append({"label": label, "old": _clip(before), "new": _clip(value), "section": section})
    for section, _, row in sorted(rows_added):
        text.append({"label": f"Added row: {row}", "old": "", "new": "", "section": section})
    for section, _, row in sorted(rows_removed):
        text.append({"label": f"Removed row: {row}", "old": "", "new": "", "section": section})

    # Sections, by heading.
    old_blocks, new_blocks = _blocks(old), _blocks(new)
    old_heads = Counter(t for k, t in old_blocks if k == "heading")
    new_heads = Counter(t for k, t in new_blocks if k == "heading")
    sections_added = list((new_heads - old_heads).elements())
    sections_removed = list((old_heads - new_heads).elements())

    # Other blocks, in order.
    a = [t for k, t in old_blocks if k == "block"]
    b = [t for k, t in new_blocks if k == "block"]
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pairs):
            before, after = a[i1 + k], b[j1 + k]
            if _skeleton(before) == _skeleton(after):
                # A lone value ("$1.255M") takes the label printed before it.
                label = ""
                if _skeleton(after).strip() in {"#", ""} and j1 + k > 0:
                    label = _clip(b[j1 + k - 1])
                numbers.extend(_number_changes(label, before, after))
            else:
                text.append({"label": "Changed", "old": _clip(before), "new": _clip(after), "section": ""})
        text.extend({"label": "Removed", "old": _clip(t), "new": "", "section": ""} for t in a[i1 + pairs:i2])
        text.extend({"label": "Added", "old": "", "new": _clip(t), "section": ""} for t in b[j1 + pairs:j2])

    # Design, separately.
    design: list[str] = []
    old_css, old_inline = _styles(old)
    new_css, new_inline = _styles(new)
    if old_css != new_css or Counter(old_inline) != Counter(new_inline):
        old_colors = Counter(c.lower() for c in _COLOR.findall(old_css + " ".join(old_inline)))
        new_colors = Counter(c.lower() for c in _COLOR.findall(new_css + " ".join(new_inline)))
        gone, came = sorted((old_colors - new_colors).keys()), sorted((new_colors - old_colors).keys())
        if gone or came:
            design.append("Colours changed: " + ", ".join(gone[:4] or ["—"]) + " → " + ", ".join(came[:4] or ["—"]))
        # Rules compared with colours masked, so a re-theme reads as one line.
        old_rules = set(_COLOR.sub("#", r).strip() for r in old_css.split("}") if r.strip())
        new_rules = set(_COLOR.sub("#", r).strip() for r in new_css.split("}") if r.strip())
        if old_rules != new_rules:
            design.append(f"Styles changed: {len(new_rules - old_rules)} rule(s) added or edited, {len(old_rules - new_rules)} removed")
        elif Counter(_COLOR.sub("#", s) for s in old_inline) != Counter(_COLOR.sub("#", s) for s in new_inline):
            design.append("Inline styling changed")
    old_title = old.title.get_text(strip=True) if old.title else ""
    new_title = new.title.get_text(strip=True) if new.title else ""

    result: dict[str, Any] = {
        "title": {"old": old_title, "new": new_title} if old_title != new_title else None,
        "numbers": numbers[:MAX_ITEMS],
        "sections_added": sections_added[:MAX_ITEMS],
        "sections_removed": sections_removed[:MAX_ITEMS],
        "text": text[:MAX_ITEMS],
        "design": design,
        "truncated": len(numbers) > MAX_ITEMS or len(text) > MAX_ITEMS,
    }
    result["summary"] = summarize(result)
    return result


def summarize(diff: dict[str, Any]) -> str:
    """One plain line: "3 figures changed (Equipment · Y2: $15,000 → $20,000, …); added section …"."""
    parts: list[str] = []
    numbers = diff.get("numbers") or []
    if numbers:
        shown = ", ".join(f"{n['label']}: {n['old']} → {n['new']}" for n in numbers[:2])
        more = f", +{len(numbers) - 2} more" if len(numbers) > 2 else ""
        parts.append(f"{len(numbers)} figure{'s' if len(numbers) != 1 else ''} changed ({shown}{more})")
    for key, verb in (("sections_added", "added"), ("sections_removed", "removed")):
        names = diff.get(key) or []
        if names:
            parts.append(f"{verb} section{'s' if len(names) != 1 else ''} " + ", ".join(f"“{n}”" for n in names[:3])
                         + (f" +{len(names) - 3}" if len(names) > 3 else ""))
    edits = diff.get("text") or []
    if edits:
        parts.append(f"{len(edits)} text edit{'s' if len(edits) != 1 else ''}")
    if diff.get("title"):
        parts.append(f"renamed to “{diff['title']['new']}”")
    if diff.get("design"):
        parts.append("design changed")
    if not parts:
        return "No visible changes."
    line = "; ".join(parts)
    return line[0].upper() + line[1:]
