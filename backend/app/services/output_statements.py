"""Split a workflow output into the statements a reader would check.

Sourcing (see ``output_sourcing``) traces each statement in a workflow's
output back to the place it came from. This module only finds the
statements, with their exact position in the output, so the run UI can
underline each one where it is shown: it never changes the output.

Two kinds of output are addressed differently, matching how the UI shows
them:

* a string (Markdown, or JSON the model wrote as text) is shown as written,
  so a statement is a character span ``[start, end)`` in the raw string;
* a structured value (a dict or list a step produced) is shown pretty-printed,
  so a statement is a JSON path to a leaf, plus a span inside that leaf
  when the leaf is a string.

A statement is a sentence, a list item, a table cell, or a JSON leaf. Each
carries the plain text a judge reads and a ``label`` naming the field, row
or column it belongs to ("Full Applications Due — Date / Time"), because a
bare cell ("2022-07-13 5:00 PM ET") says nothing on its own.

``kind`` says what the statement can be checked for:

* ``claim``   — a statement of fact; the only kind sent to the judge.
* ``absent``  — "Not specified in the document" and the like: a claim that
  something is missing, which no passage can show.
* ``verdict`` — a judgment ("Pass", "Allowable", ``true``) drawn from facts
  rather than stated in a source.

Pure string logic, no I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MAX_STATEMENTS = 500          # per output; the rest are left unsourced
MAX_STATEMENT_CHARS = 700     # longer runs of text are not one checkable fact
SHORT_LEAF_CHARS = 240        # a string leaf up to this long is one statement


@dataclass
class Statement:
    start: int | None
    end: int | None
    text: str
    label: str = ""
    path: list | None = None
    kind: str = "claim"
    # Set by the caller for its own bookkeeping (cache key, result).
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# What a statement is
# ---------------------------------------------------------------------------

_ABSENT_RE = re.compile(
    r"^(?:not\s+(?:specified|stated|found|provided|mentioned|given|applicable|available|identified|listed|indicated|addressed|enumerated)"
    r"|none(?:\s+(?:explicitly\s+)?(?:enumerated|stated|specified|identified|listed|found|provided|mentioned))?"
    r"|no\s+(?:information|data|value|entry|mention)"
    r"|n/?a|unknown|missing|tbd|null)\b",
    re.IGNORECASE,
)

# Judgments a workflow draws from facts. Short on purpose: "Required" or
# "Grant" can be read straight off a source, these cannot.
_VERDICTS = frozenset({
    "yes", "no", "true", "false", "pass", "passed", "fail", "failed", "met", "not met",
    "partially met", "allowable", "unallowable", "not allowable", "allowed", "not allowed",
    "compliant", "noncompliant", "non-compliant", "eligible", "ineligible", "not eligible",
    "needs info", "needs_info", "missing info", "insufficient information", "ok", "high",
    "medium", "moderate", "low", "approve", "approved", "reject", "rejected", "flag",
    "flagged", "not flagged", "triggered", "not triggered", "applicable", "not applicable",
    "satisfied", "not satisfied", "unclear", "uncertain", "conditional", "warning", "risk",
})


# A machine token ("expense:transaction_date", "award_terms", "KB2"): a key
# or pointer the workflow wrote, not something a reader would check.
_IDENTIFIER_RE = re.compile(r"^(?:[a-z][a-z0-9]*(?:[_:][a-z0-9]+)+|KB\d+|kb\d+)$")
# JSON fields that hold identifiers rather than statements.
_ID_KEY_RE = re.compile(r"(?:^|_)(?:id|ids|uuid|key|code|slug|source_label)$", re.IGNORECASE)


def classify(text: str) -> str:
    raw = (text or "").strip()
    t = re.sub(r"[\s*_`.:;!]+$", "", raw).strip(" *_`")
    if not re.search(r"[A-Za-z0-9]", t):
        return "skip"
    low = t.lower()
    if low in _VERDICTS or low.replace("_", " ") in _VERDICTS:
        return "verdict"
    if _IDENTIFIER_RE.match(t):
        return "skip"
    if raw.endswith(":") and len(t) <= 80:
        return "skip"   # a lead-in ("Check results:"), not a statement
    if _ABSENT_RE.match(low):
        return "absent"
    if len(t) > MAX_STATEMENT_CHARS:
        return "skip"
    return "claim"


# ---------------------------------------------------------------------------
# Inline Markdown
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"!?\[([^\]\n]*)\]\((?:[^()\s]|\([^)]*\))*(?:\s+\"[^\"]*\")?\)")
_CITATION_RE = re.compile(r"\[[^\[\]\n]{2,300}\](?!\()")
_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]{0,200}>")
_EMPH_OPEN_RE = re.compile(r"(?<![\w\\])(\*\*|__|\*|_|~~)(?=\S)")
_EMPH_CLOSE_RE = re.compile(r"(?<=\S)(\*\*|__|\*|_|~~)(?![\w])")


def plain(md: str) -> str:
    """What ``md`` reads as once rendered: links keep their text, emphasis
    and code marks go, bracketed citations (older runs wrote them inline)
    are dropped so their "part 46" is not taken for a value."""
    t = _LINK_RE.sub(lambda m: m.group(1), md or "")
    t = _CITATION_RE.sub(" ", t)
    t = _TAG_RE.sub(" ", t)
    t = t.replace("\\|", "|").replace("`", "")
    t = _EMPH_OPEN_RE.sub("", t)
    t = _EMPH_CLOSE_RE.sub("", t)
    t = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


_TRIM_LEAD = " \t*_`>~"
_TRIM_TAIL = " \t*_`~"
_TRAILING_CITES_RE = re.compile(r"(?:\s*\[[^\[\]\n]{2,300}\](?!\())+\s*[.;,]?\s*$")


def _trim(s: str, start: int, end: int) -> tuple[int, int]:
    """Shrink ``[start, end)`` past surrounding whitespace, emphasis marks and
    any bracketed citations it ends with (the UI draws those as chips)."""
    m = _TRAILING_CITES_RE.search(s, start, end)
    if m and m.start() > start:
        end = m.start()
    while start < end and s[start] in _TRIM_LEAD:
        start += 1
    while end > start and s[end - 1] in _TRIM_TAIL:
        end -= 1
    # An emphasis run opened before the span and closed inside it ("**Grant"
    # after trimming the "**" prefix) leaves a dangling mark; harmless for
    # the span, so nothing more to do.
    return start, end


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------

_ABBREV = frozenset({
    "u.s", "e.g", "i.e", "etc", "vs", "no", "nos", "dr", "mr", "mrs", "ms", "st", "inc",
    "ltd", "co", "corp", "jr", "sr", "p.m", "a.m", "approx", "dept", "fig", "sec", "art",
    "vol", "pp", "p", "cf", "al", "est", "min", "max", "jan", "feb", "mar", "apr", "jun",
    "jul", "aug", "sep", "sept", "oct", "nov", "dec", "ph.d", "u.s.c", "c.f.r", "govt",
})
_BOUNDARY_RE = re.compile(r"[.!?][\"'”’)\]*_]*\s+(?=[\"“'‘(*_\[]*[A-Z0-9])")


def sentence_spans(s: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Sentence spans of ``s[start:end]``, as offsets into ``s``."""
    end = len(s) if end is None else end
    spans: list[tuple[int, int]] = []
    cur = start
    for m in _BOUNDARY_RE.finditer(s, start, end):
        before = s[cur:m.start()]
        tok = re.search(r"(\S+)$", before)
        word = tok.group(1).lower().lstrip("(*_\"“'") if tok else ""
        # "non‑U.S." ends in the abbreviation, not in "non".
        word = re.split(r"[-‐‑‒–—/]", word)[-1]
        if word in _ABBREV or re.fullmatch(r"[a-z]", word) or re.fullmatch(r"(?:[a-z]\.)+[a-z]", word):
            continue
        stop = m.end()
        while stop > m.start() and s[stop - 1].isspace():
            stop -= 1
        spans.append((cur, stop))
        cur = m.end()
    spans.append((cur, end))
    out = []
    for a, b in spans:
        a, b = _trim(s, a, b)
        if b > a:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?")
_QUOTE_RE = re.compile(r"^\s{0,3}(?:>\s?)+")
_JSON_LINE_RE = re.compile(r'^\s*"((?:[^"\\]|\\.){1,120})"\s*:\s*')
_BOLD_LABEL_RE = re.compile(
    r"^(\*\*|__)([^*_\n]{1,100}?)(:?)\1\s*(?:(:)|[—–]|-{1,2}(?=\s))?\s*"
)
_PLAIN_LABEL_RE = re.compile(r"^([A-Z][A-Za-z0-9 /&()'’.,#-]{0,60}?):\s+(?=\S)")


def _lines(text: str) -> list[tuple[int, str]]:
    out = []
    pos = 0
    for line in text.split("\n"):
        out.append((pos, line))
        pos += len(line) + 1
    return out


def _cells(line: str, off: int) -> list[tuple[int, int]]:
    """Raw spans of a table row's cells (escaped pipes stay inside a cell)."""
    bounds = [i for i, ch in enumerate(line) if ch == "|" and (i == 0 or line[i - 1] != "\\")]
    s = line
    first = len(s) - len(s.lstrip())
    edges = [first - 1] if not (bounds and bounds[0] == first) else []
    edges += bounds
    last = len(s.rstrip())
    if not (bounds and bounds[-1] == last - 1):
        edges.append(last)
    spans = []
    for a, b in zip(edges, edges[1:]):
        spans.append((off + a + 1, off + b))
    return spans


def _add(out: list[Statement], text: str, a: int, b: int, label: str, base: int = 0) -> None:
    a, b = _trim(text, a, b)
    if b <= a:
        return
    p = plain(text[a:b])
    kind = classify(p)
    if kind == "skip":
        return
    out.append(Statement(base + a, base + b, p, label=label, kind=kind))


def _content(out: list[Statement], text: str, a: int, b: int, label: str, base: int) -> None:
    """A list item's or paragraph's text: a leading "Label:" names the field;
    the rest is one statement per sentence."""
    seg = text[a:b]
    a += len(seg) - len(seg.lstrip())
    seg = text[a:b]
    bold = _BOLD_LABEL_RE.match(seg)
    plain_label = None if bold else _PLAIN_LABEL_RE.match(seg)
    if bold and seg[bold.end():].strip():
        # "**Sponsor:** X", "**Sponsor**: X", "**Cost share** — X"; a bold
        # phrase with no separator is the statement itself.
        if bold.group(3) or bold.group(4) or re.search(r"[—–-]\s*$", bold.group(0)):
            label = _join_label(label, plain(bold.group(2)))
            a += bold.end()
    elif plain_label and seg[plain_label.end():].strip():
        label = _join_label(label, plain_label.group(1).strip())
        a += plain_label.end()
    if a >= b:
        return
    whole = plain(text[a:b])
    if len(whole) <= 160 and classify(whole) != "claim":
        _add(out, text, a, b, label, base)
        return
    for sa, sb in sentence_spans(text, a, b):
        _add(out, text, sa, sb, label, base)


def _join_label(*parts: str) -> str:
    return " — ".join(p for p in parts if p)


def markdown_statements(text: str, base: int = 0, label: str = "") -> list[Statement]:
    """Statements in Markdown ``text``: sentences of paragraphs and list
    items, and table cells, as spans offset by ``base``."""
    out: list[Statement] = []
    lines = _lines(text)
    in_fence = False
    i = 0
    while i < len(lines):
        off, line = lines[i]
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            _json_line(out, text, off, line, label, base)
            i += 1
            continue
        if not line.strip() or _HR_RE.match(line) or _HEADING_RE.match(line):
            i += 1
            continue
        # A table: a header row, then a separator row, then body rows.
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1][1]):
            headers = [plain(text[a:b]) for a, b in _cells(line, off)]
            i += 2
            while i < len(lines) and "|" in lines[i][1] and lines[i][1].strip():
                roff, row = lines[i]
                cells = _cells(row, roff)
                row_label = plain(text[cells[0][0]:cells[0][1]]) if cells else ""
                for c, (a, b) in enumerate(cells):
                    if c == 0 and len(cells) > 1:
                        continue   # the row's name: the label, not a statement
                    col = headers[c] if c < len(headers) else ""
                    if _PROVENANCE_HEADER_RE.match(col.strip()):
                        continue
                    cell_label = _join_label(label, row_label if len(cells) > 1 else "", col)
                    cell_plain = plain(text[a:b])
                    if len(cell_plain) <= SHORT_LEAF_CHARS:
                        _add(out, text, a, b, cell_label, base)
                    else:
                        for sa, sb in sentence_spans(text, a, b):
                            _add(out, text, sa, sb, cell_label, base)
                i += 1
            continue
        if _json_line(out, text, off, line, label, base):
            i += 1
            continue
        a = off
        rest = line
        q = _QUOTE_RE.match(rest)
        if q:
            a += q.end()
            rest = rest[q.end():]
        li = _LIST_RE.match(rest)
        if li:
            a += li.end()
        _content(out, text, a, off + len(line), label, base)
        i += 1
    return out


def _json_line(out: list[Statement], text: str, off: int, line: str, label: str, base: int) -> bool:
    """A ``"key": value,`` line of JSON written into Markdown or a code
    block: the value is the statement, the key its label."""
    m = _JSON_LINE_RE.match(line)
    if not m:
        return False
    key = _humanize(_unescape(m.group(1)))
    rest_at = m.end()
    rest = line[rest_at:].rstrip()
    if rest.endswith(","):
        rest = rest[:-1].rstrip()
    lab = _join_label(label, key)
    if rest.startswith('"') and rest.endswith('"') and len(rest) >= 2:
        a, b = off + rest_at + 1, off + rest_at + len(rest) - 1
        decoded = _unescape(text[a:b])
        kind = classify(decoded)
        if kind != "skip" and b > a:
            if len(decoded) <= SHORT_LEAF_CHARS:
                out.append(Statement(base + a, base + b, plain(decoded), label=lab, kind=kind))
            else:
                for sa, sb in sentence_spans(text, a, b):
                    _add(out, text, sa, sb, lab, base)
        return True
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", rest):
        a = off + rest_at
        out.append(Statement(base + a, base + a + len(rest), rest, label=lab, kind="claim"))
        return True
    if rest in ("true", "false"):
        a = off + rest_at
        out.append(Statement(base + a, base + a + len(rest), rest, label=lab, kind="verdict"))
        return True
    return True   # null, or an object/array opening: nothing to check here


def _unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s


def _humanize(key: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", str(key))).strip()


# ---------------------------------------------------------------------------
# JSON written as text: a parser that keeps positions
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_WS = " \t\n\r"


class _JSONPos:
    """Just enough of a JSON parser to know where every leaf is.

    A node is ``(kind, value, start, end, extra)``: for a string ``value`` is
    the decoded text and ``extra`` maps each decoded character to its raw
    offset (one entry past the end, too); for an object ``value`` is
    ``[(key, node)]``; for an array ``[node]``.
    """

    def __init__(self, s: str) -> None:
        self.s = s

    def ws(self, i: int) -> int:
        while i < len(self.s) and self.s[i] in _WS:
            i += 1
        return i

    def value(self, i: int):
        i = self.ws(i)
        if i >= len(self.s):
            raise ValueError("eof")
        ch = self.s[i]
        if ch == "{":
            return self.obj(i)
        if ch == "[":
            return self.arr(i)
        if ch == '"':
            return self.string(i)
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if self.s.startswith(lit, i):
                return ("lit", val, i, i + len(lit), None), i + len(lit)
        m = _NUM_RE.match(self.s, i)
        if m:
            return ("num", m.group(), i, m.end(), None), m.end()
        raise ValueError(f"unexpected {ch!r} at {i}")

    def obj(self, i: int):
        start = i
        items = []
        i = self.ws(i + 1)
        if self.s[i:i + 1] == "}":
            return ("obj", items, start, i + 1, None), i + 1
        while True:
            key, i = self.string(self.ws(i))
            i = self.ws(i)
            if self.s[i:i + 1] != ":":
                raise ValueError("expected :")
            node, i = self.value(i + 1)
            items.append((key[1], node))
            i = self.ws(i)
            ch = self.s[i:i + 1]
            if ch == ",":
                i += 1
                continue
            if ch == "}":
                return ("obj", items, start, i + 1, None), i + 1
            raise ValueError("expected , or }")

    def arr(self, i: int):
        start = i
        items = []
        i = self.ws(i + 1)
        if self.s[i:i + 1] == "]":
            return ("arr", items, start, i + 1, None), i + 1
        while True:
            node, i = self.value(i)
            items.append(node)
            i = self.ws(i)
            ch = self.s[i:i + 1]
            if ch == ",":
                i += 1
                continue
            if ch == "]":
                return ("arr", items, start, i + 1, None), i + 1
            raise ValueError("expected , or ]")

    _ESC = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}

    def string(self, i: int):
        if self.s[i:i + 1] != '"':
            raise ValueError("expected string")
        start = i
        i += 1
        chars: list[str] = []
        where: list[int] = []
        while True:
            if i >= len(self.s):
                raise ValueError("unterminated string")
            ch = self.s[i]
            if ch == '"':
                where.append(i)
                return ("str", "".join(chars), start, i + 1, where), i + 1
            if ch == "\\":
                nxt = self.s[i + 1:i + 2]
                if nxt == "u":
                    code = int(self.s[i + 2:i + 6], 16)
                    width = 6
                    if 0xD800 <= code <= 0xDBFF and self.s[i + 6:i + 8] == "\\u":
                        low = int(self.s[i + 8:i + 12], 16)
                        code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                        width = 12
                    chars.append(chr(code))
                    where.append(i)
                    i += width
                    continue
                if nxt not in self._ESC:
                    raise ValueError("bad escape")
                chars.append(self._ESC[nxt])
                where.append(i)
                i += 2
                continue
            chars.append(ch)
            where.append(i)
            i += 1


def parse_json_positions(text: str):
    """The positional tree of ``text`` when it is one JSON object or array
    (optionally inside a ```json fence), else None."""
    s = text
    m = re.match(r"^\s*```[A-Za-z]*\s*\n", s)
    lo = m.end() if m else 0
    hi = len(s)
    if m:
        close = s.rfind("```")
        if close <= lo:
            return None
        hi = close
    i = lo
    while i < hi and s[i] in _WS:
        i += 1
    if i >= hi or s[i] not in "{[":
        return None
    try:
        node, end = _JSONPos(s).value(i)
    except (ValueError, IndexError):
        return None
    if s[end:hi].strip():
        return None
    return node


# Keys whose value names the object it sits in ("item": "Full Applications
# Due"), so a sibling leaf reads as that thing's field.
_IDENT_KEYS = (
    "name", "title", "item", "category", "label", "field", "check", "check_name",
    "requirement", "component", "event", "deadline", "type", "role", "heading", "section",
    "topic", "question", "criterion", "rule", "cost", "expense",
    # Last: which record an object was read from ("source_document":
    # "Expense Record"), so its "currency" is not checked against the award.
    "source_document",
)

# A table column that says where the model got a row ("Source:
# Announcement") annotates the row; it is not a statement about the subject.
_PROVENANCE_HEADER_RE = re.compile(r"^(?:sources?|references?|citations?|cited|page|pages|p\.)$", re.IGNORECASE)


def _ident(items: list, skip_key: str) -> str:
    """What an object is about, from a naming sibling of ``skip_key``."""
    for want in _IDENT_KEYS:
        for k, v in items:
            if k == skip_key or str(k).lower() != want:
                continue
            text = v if isinstance(v, str) else (v[1] if isinstance(v, tuple) and v[0] == "str" else None)
            if isinstance(text, str) and 0 < len(text) <= 100:
                return text.strip()
    return ""


def _leaf_label(prefix: str, key, items: list | None) -> str:
    parts = [prefix] if prefix else []
    if items is not None:
        ident = _ident(items, key)
        if ident:
            parts.append(ident)
    if key is not None and not isinstance(key, int):
        parts.append(_humanize(key))
    return " — ".join(p for p in parts if p)


def _string_statements(value: str, label: str) -> list[Statement]:
    """Statements inside a string leaf, as spans of the decoded string."""
    stripped = value.strip()
    if stripped[:1] in "{[" or stripped.startswith("```"):
        node = parse_json_positions(value)
        if node is not None:
            return _positional_statements(node, label, [])
    if "\n" in value or len(value) > SHORT_LEAF_CHARS:
        return markdown_statements(value, 0, label)
    a, b = _trim(value, 0, len(value))
    if b <= a:
        return []
    spans = sentence_spans(value, a, b)
    if len(spans) <= 1:
        p = plain(value[a:b])
        kind = classify(p)
        return [] if kind == "skip" else [Statement(a, b, p, label=label, kind=kind)]
    out: list[Statement] = []
    for sa, sb in spans:
        _add(out, value, sa, sb, label)
    return out


def _positional_statements(node, label: str, path: list) -> list[Statement]:
    """Statements of a positional JSON tree, as raw offsets into its text."""
    kind = node[0]
    out: list[Statement] = []
    if kind == "obj":
        for key, child in node[1]:
            if child[0] not in ("obj", "arr") and _ID_KEY_RE.search(str(key)):
                continue
            lab = _leaf_label(label, key, node[1]) if child[0] not in ("obj", "arr") else _join_label(label, _humanize(key))
            out.extend(_positional_statements(child, lab, path + [key]))
    elif kind == "arr":
        for idx, child in enumerate(node[1]):
            out.extend(_positional_statements(child, label, path + [idx]))
    elif kind == "str":
        where = node[4]
        for st in _string_statements(node[1], label):
            st.start, st.end = where[st.start], where[st.end - 1] + _raw_width(node, st.end - 1)
            st.path = path
            out.append(st)
    elif kind == "num":
        out.append(Statement(node[2], node[3], node[1], label=label, path=path, kind="claim"))
    elif kind == "lit" and node[1] is not None:
        out.append(Statement(node[2], node[3], "true" if node[1] else "false", label=label, path=path, kind="verdict"))
    return out


def _raw_width(node, idx: int) -> int:
    """How many raw characters decoded character ``idx`` of a string node
    took (1, or the length of its escape)."""
    where = node[4]
    return where[idx + 1] - where[idx]


# ---------------------------------------------------------------------------
# Structured values (shown pretty-printed): addressed by path
# ---------------------------------------------------------------------------

def _value_statements(value, label: str, path: list, items: list | None, key) -> list[Statement]:
    out: list[Statement] = []
    if isinstance(value, dict):
        pairs = list(value.items())
        for k, v in pairs:
            if not isinstance(v, (dict, list)) and _ID_KEY_RE.search(str(k)):
                continue
            lab = _leaf_label(label, k, pairs) if not isinstance(v, (dict, list)) else _join_label(label, _humanize(k))
            out.extend(_value_statements(v, lab, path + [k], pairs, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(_value_statements(v, label, path + [i], None, i))
    elif isinstance(value, str):
        for st in _string_statements(value, label):
            st.path = path
            out.append(st)
    elif isinstance(value, bool):
        out.append(Statement(None, None, "true" if value else "false", label=label, path=path, kind="verdict"))
    elif isinstance(value, (int, float)):
        out.append(Statement(None, None, json.dumps(value), label=label, path=path, kind="claim"))
    return out


def split_output(value) -> tuple[str, list[Statement]]:
    """``(format, statements)`` for an output value.

    ``format`` is ``text`` (spans into the string), ``json`` (paths into a
    structured value) or ``none`` (a file, or nothing to check)."""
    if isinstance(value, str):
        node = parse_json_positions(value)
        stmts = _positional_statements(node, "", []) if node is not None else markdown_statements(value)
        return "text", stmts[:MAX_STATEMENTS]
    if isinstance(value, dict) and value.get("type") == "file_download":
        return "none", []
    if isinstance(value, (dict, list)):
        return "json", _value_statements(value, "", [], None, None)[:MAX_STATEMENTS]
    return "none", []
