"""Screen a fetched web page for content a reader of the page never sees.

A knowledge base answers everyone who uses it, so a page that carries text a
human cannot see, such as white-on-white text, zero-size text, or a paragraph
pushed off-screen, changes those answers without anyone having read what
changed them. Trafilatura only drops elements hidden by an inline
``display:none``; every other technique reaches the index intact. This module
finds two things and reports them so ingestion can hold the page for the
user to look at before it is embedded:

* **Hidden text**: rendered text that cannot be seen. This is a structural
  signal (CSS a browser would apply), not a judgement about wording, and is
  the load-bearing check.
* **Text addressed to an AI**: wording that speaks to the model reading the
  page ("note to the AI", "ignore all previous instructions", chat-template
  tokens), wherever it sits on the page.

What it deliberately does not flag:

* ``display:none``, ``visibility:hidden`` and the ``hidden`` attribute.
  These are how accordions, tabs and menus hide text the reader opens with
  a click, which is the normal shape of an FAQ page. Trafilatura already
  drops the inline form.
* Short screen-reader labels ("Skip to main content", "Opens in a new
  window"). They are hidden by design, carry no claim, and sit below
  ``_MIN_HIDDEN_CHARS``.
* Hidden text that never reaches the indexed text, or that repeats text
  the page also shows. Neither changes what the knowledge base says.
* Instructions addressed to people. Research-administration pages are made
  of them ("You must report any change in PI effort within 30 days"), and a
  line-level pattern cannot tell those apart from an instruction aimed at a
  model (see the note above ``INJECTION_CLAUSE`` in ``extraction_engine.py``).
  The instruction check therefore matches only wording that names the
  reader as an AI. It is a heuristic with known evasions: a payload phrased
  as an ordinary correction notice passes. That is why hidden text, which
  does not depend on wording, is checked separately.

Only inline styles and the page's own ``<style>`` blocks are read. External
stylesheets are not fetched, so text hidden only by an external rule is not
seen.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

KIND_HIDDEN_TEXT = "hidden_text"
KIND_INSTRUCTION_TEXT = "instruction_text"

# Hidden runs shorter than this are screen-reader labels and icon text.
_MIN_HIDDEN_CHARS = 25
_MIN_HIDDEN_WORDS = 4
_EXCERPT_CHARS = 300
_MAX_FINDINGS = 10

# Below this the text is unreadable at any zoom.
_MIN_VISIBLE_FONT_PX = 1.5
_DEFAULT_FONT_PX = 16.0
# Opacity or color alpha at or below this is not visible.
_MAX_INVISIBLE_ALPHA = 0.05
# An offset this far negative puts the box outside any viewport.
_OFFSCREEN_PX = -500.0
# Every channel at or above this counts as white.
_NEAR_WHITE_CHANNEL = 240

_SKIP_TAGS = {"script", "style", "noscript", "template", "head", "title", "meta", "link"}

_NAMED_WHITE = {"white", "snow", "ivory", "ghostwhite", "whitesmoke", "floralwhite", "mintcream", "azure"}

def _phrase(pattern: str) -> re.Pattern[str]:
    """Compile with every literal space matching any whitespace run, so a
    line break or doubled space inside a phrase does not hide it."""
    return re.compile(pattern.replace(" ", r"\s+"), re.I)


# Model-addressed wording only; see the module docstring for why.
_AI = r"(?:ai|a\.i\.|llm|large language model|language model|chat-?bot|chatgpt|gpt|claude|gemini|copilot|ai assistant|ai model|ai agent)"
_INSTRUCTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_phrase(
        r"\bignore (?:all |any )?(?:of )?(?:the |your |these )?"
        r"(?:previous|prior|above|preceding|earlier|other|system) "
        r"(?:instructions|prompts?|messages|context|directions)\b"),
     "tells the reader to ignore its previous instructions"),
    (_phrase(
        rf"\b(?:note|message|instructions?|attention|notice|directions?) (?:to|for) "
        rf"(?:the |any |all )?{_AI}s?\b"),
     "is addressed to an AI"),
    (_phrase(
        rf"\b(?:you are|you're|act as|acting as|as) (?:an?|the) {_AI}\b"),
     "is addressed to an AI"),
    (_phrase(
        rf"\b(?:if|when|any|all) (?:an? |the )?{_AI}s? "
        r"(?:is |are )?(?:reading|reads|processing|processes|summari[sz]ing|summari[sz]es|"
        r"parsing|ingesting|asked|answering|responding)\b"),
     "is addressed to an AI"),
    (_phrase(
        r"\b(?:system|developer) (?:prompt|message|instructions?)\s*:|"
        r"\b(?:reveal|override|replace|ignore) (?:your|the) system prompt\b"),
     "imitates a system prompt"),
    (_phrase(
        r"\b(?:do not|don't|never) (?:tell|inform|mention (?:this |it )?to|reveal (?:this |it )?to|disclose (?:this |it )?to) "
        r"the user\b"),
     "tells the reader to keep something from the user"),
    (_phrase(r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[/?INST\]|<<SYS>>|</?system>"),
     "contains chat-template control tokens"),
]


@dataclass(frozen=True)
class PageFinding:
    """One reason a fetched page should be looked at before it is indexed."""
    kind: str        # KIND_HIDDEN_TEXT | KIND_INSTRUCTION_TEXT
    reason: str      # "white text", "is addressed to an AI", ...
    excerpt: str     # the text itself, as it would be indexed
    fingerprint: str  # stable across refetches of the same text

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "reason": self.reason,
            "excerpt": self.excerpt, "fingerprint": self.fingerprint,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(kind: str, excerpt: str) -> str:
    return hashlib.sha256(f"{kind}\0{_norm(excerpt).casefold()}".encode()).hexdigest()[:24]


def _finding(kind: str, reason: str, text: str) -> PageFinding:
    excerpt = _norm(text)
    if len(excerpt) > _EXCERPT_CHARS:
        excerpt = excerpt[: _EXCERPT_CHARS - 1].rstrip() + "…"
    return PageFinding(kind, reason, excerpt, _fingerprint(kind, _norm(text)))


# --- CSS -------------------------------------------------------------------

def _parse_declarations(style: str) -> dict[str, str]:
    decls: dict[str, str] = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        prop, _, value = part.partition(":")
        value = re.sub(r"\s*!important\s*$", "", value.strip(), flags=re.I)
        if prop.strip():
            decls[prop.strip().lower()] = value.lower()
    return decls


_SIMPLE_SELECTOR = re.compile(r"^([a-z][a-z0-9-]*)?((?:[.#][\w-]+)*)$", re.I)


def _parse_stylesheets(soup: BeautifulSoup) -> list[tuple[Optional[str], list[str], dict[str, str]]]:
    """Rules from the page's ``<style>`` blocks whose selectors are a single
    compound (``p``, ``.cls``, ``#id``, ``span.a.b``). Descendant and
    pseudo-class selectors are skipped rather than guessed at."""
    rules: list[tuple[Optional[str], list[str], dict[str, str]]] = []
    for style in soup.find_all("style"):
        css = re.sub(r"/\*.*?\*/", "", style.get_text() or "", flags=re.S)
        # [^{}] keeps only innermost blocks, which also unwraps @media.
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            decls = _parse_declarations(body)
            if not decls:
                continue
            for sel in selectors.split(","):
                m = _SIMPLE_SELECTOR.match(sel.strip())
                if not m or not sel.strip() or sel.strip().startswith("@"):
                    continue
                tag = (m.group(1) or "").lower() or None
                parts = re.findall(r"[.#][\w-]+", m.group(2) or "")
                rules.append((tag, parts, decls))
    return rules


def _matches(el: Tag, tag: Optional[str], parts: list[str]) -> bool:
    if tag and el.name != tag:
        return False
    classes = el.get("class") or []
    for p in parts:
        if p[0] == "." and p[1:] not in classes:
            return False
        if p[0] == "#" and el.get("id") != p[1:]:
            return False
    return bool(tag or parts)


def _declarations_for(el: Tag, rules) -> dict[str, str]:
    decls: dict[str, str] = {}
    for tag, parts, rule in rules:
        if _matches(el, tag, parts):
            decls.update(rule)
    style = el.get("style")
    if isinstance(style, str):
        decls.update(_parse_declarations(style))  # inline wins
    return decls


def _length_px(value: str, parent_px: float) -> Optional[float]:
    m = re.match(r"^(-?\d*\.?\d+)\s*(px|pt|em|rem|%|vw|vh)?$", value.strip())
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2) or "px"
    if unit == "pt":
        return n * 4 / 3
    if unit == "em":
        return n * parent_px
    if unit == "rem":
        return n * _DEFAULT_FONT_PX
    if unit == "%":
        return n / 100 * parent_px
    if unit in ("vw", "vh"):
        return n * 10  # any nonzero viewport unit is readable; 0 is not
    return n


def _rgba(value: str) -> Optional[tuple[int, int, int, float]]:
    v = value.strip()
    if v == "transparent":
        return (0, 0, 0, 0.0)
    if v in _NAMED_WHITE:
        return (255, 255, 255, 1.0)
    m = re.match(r"^#([0-9a-f]{3,8})$", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.match(r"^rgba?\(([^)]*)\)$", v)
    if m:
        nums = [x for x in re.split(r"[\s,/]+", m.group(1).strip()) if x]
        try:
            rgb = [int(float(x.rstrip("%")) * (2.55 if x.endswith("%") else 1)) for x in nums[:3]]
            a = 1.0
            if len(nums) > 3:
                a = float(nums[3].rstrip("%")) / (100 if nums[3].endswith("%") else 1)
            return (rgb[0], rgb[1], rgb[2], a)
        except (ValueError, IndexError):
            return None
    m = re.match(r"^hsla?\(([^)]*)\)$", v)
    if m:
        nums = [x for x in re.split(r"[\s,/]+", m.group(1).strip()) if x]
        try:
            light = float(nums[2].rstrip("%"))
            a = float(nums[3].rstrip("%")) / (100 if nums[3].endswith("%") else 1) if len(nums) > 3 else 1.0
            return (255, 255, 255, a) if light >= 95 else (0, 0, 0, a)
        except (ValueError, IndexError):
            return None
    return None


def _is_white(rgba) -> bool:
    return rgba is not None and rgba[3] > _MAX_INVISIBLE_ALPHA and min(rgba[:3]) >= _NEAR_WHITE_CHANNEL


def _background(decls: dict[str, str]) -> Optional[str]:
    """``"white"``, ``"other"`` (a color or image that may sit behind light
    text), or None when the element declares no background."""
    for prop in ("background-color", "background"):
        value = decls.get(prop)
        if not value:
            continue
        if "url(" in value or "gradient(" in value:
            return "other"
        first = value.split()[0] if prop == "background" else value
        rgba = _rgba(first)
        if rgba is None:
            return "other" if prop == "background-color" else None
        if rgba[3] <= _MAX_INVISIBLE_ALPHA:
            continue  # transparent: whatever is behind shows through
        return "white" if _is_white(rgba) else "other"
    return None


def _offscreen(decls: dict[str, str], font_px: float) -> bool:
    if decls.get("position") in ("absolute", "fixed"):
        for side in ("left", "top", "right"):
            px = _length_px(decls.get(side, ""), font_px)
            if px is not None and px <= _OFFSCREEN_PX:
                return True
    indent = _length_px(decls.get("text-indent", ""), font_px)
    if indent is not None and indent <= _OFFSCREEN_PX:
        return True
    margin = _length_px(decls.get("margin-left", ""), font_px)
    if margin is not None and margin <= _OFFSCREEN_PX * 2:
        return True
    transform = decls.get("transform", "")
    m = re.search(r"translate(?:x|3d)?\(\s*(-?\d+\.?\d*)px", transform)
    return bool(m and float(m.group(1)) <= _OFFSCREEN_PX)


def _clipped(decls: dict[str, str], font_px: float) -> bool:
    clip = decls.get("clip", "").replace(" ", "")
    if re.match(r"^rect\((0(px)?,?){4}\)$", clip):
        return True
    clip_path = decls.get("clip-path", "").replace(" ", "")
    if clip_path in ("inset(50%)", "inset(100%)", "circle(0)", "circle(0px)", "polygon(0000)"):
        return True
    if decls.get("overflow") in ("hidden", "clip"):
        for prop in ("width", "height", "max-width", "max-height"):
            px = _length_px(decls.get(prop, ""), font_px)
            if px is not None and px <= 1:
                return True
    return False


@dataclass
class _State:
    font_px: float = _DEFAULT_FONT_PX
    font_anchor: Optional[int] = None
    opacity: float = 1.0
    color: Optional[tuple] = None
    color_anchor: Optional[int] = None
    background: Optional[str] = None  # nearest declared background
    clip_reason: Optional[str] = None
    clip_anchor: Optional[int] = None


def _walk(el: Tag, state: _State, rules, hidden: dict, visible: list[str]) -> None:
    decls = _declarations_for(el, rules)
    s = _State(**state.__dict__)
    anchor = id(el)
    size = decls.get("font-size")
    if size:
        px = _length_px(size, state.font_px)
        if px is not None:
            s.font_px, s.font_anchor = px, anchor
    try:
        s.opacity *= max(0.0, min(1.0, float(decls.get("opacity", "1").rstrip("%")) / (100 if decls.get("opacity", "").endswith("%") else 1)))
    except ValueError:
        pass
    if decls.get("color"):
        rgba = _rgba(decls["color"])
        if rgba is not None:
            s.color, s.color_anchor = rgba, anchor
    bg = _background(decls)
    if bg:
        s.background = bg
    if s.clip_reason is None:
        if s.opacity <= _MAX_INVISIBLE_ALPHA:
            s.clip_reason, s.clip_anchor = "transparent text", anchor
        elif _offscreen(decls, s.font_px):
            s.clip_reason, s.clip_anchor = "text positioned off-screen", anchor
        elif _clipped(decls, s.font_px):
            s.clip_reason, s.clip_anchor = "text clipped to nothing", anchor

    for child in el.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            text = str(child)
            if not text.strip():
                continue
            reason, key = _hidden_reason(s, anchor)
            if reason:
                hidden.setdefault(key, (reason, []))[1].append(text)
            else:
                visible.append(text)
        elif isinstance(child, Tag) and child.name not in _SKIP_TAGS:
            _walk(child, s, rules, hidden, visible)


def _hidden_reason(s: _State, anchor: int) -> tuple[Optional[str], Optional[int]]:
    if s.clip_reason:
        return s.clip_reason, s.clip_anchor
    if s.font_px < _MIN_VISIBLE_FONT_PX:
        return "zero-size text", s.font_anchor or anchor
    if s.color is not None:
        if s.color[3] <= _MAX_INVISIBLE_ALPHA:
            return "transparent text", s.color_anchor
        # White text is hidden unless something behind it is not white.
        # Only backgrounds this page declares are known; light text over
        # a dark hero styled by an external sheet will read as hidden.
        if _is_white(s.color) and s.background != "other":
            return "white text on a white background", s.color_anchor
    return None, None


def find_hidden_text(raw_html: str, indexed_text: str) -> list[PageFinding]:
    """Hidden runs of ``raw_html`` that made it into ``indexed_text``."""
    if not raw_html or not indexed_text:
        return []
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
    except Exception:
        return []
    rules = _parse_stylesheets(soup)
    root = soup.body or soup
    hidden: dict[int, tuple[str, list[str]]] = {}
    visible: list[str] = []
    if isinstance(root, Tag):
        _walk(root, _State(), rules, hidden, visible)

    indexed = _norm(indexed_text).casefold()
    shown = _norm(" ".join(visible)).casefold()
    findings: list[PageFinding] = []
    seen: set[str] = set()
    for reason, parts in hidden.values():
        text = _norm(" ".join(parts))
        if len(text) < _MIN_HIDDEN_CHARS or len(text.split()) < _MIN_HIDDEN_WORDS:
            continue
        key = text.casefold()
        # Trafilatura may split a run across lines, so the head of the run
        # stands in for the whole when matching it against the index.
        probe = key[:80]
        if probe not in indexed or key in shown:
            continue
        f = _finding(KIND_HIDDEN_TEXT, reason, text)
        if f.fingerprint not in seen:
            seen.add(f.fingerprint)
            findings.append(f)
    return findings


# --- Instruction-like wording ----------------------------------------------

def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(c, 0, start) for c in ".!?\n")
    right_candidates = [i for i in (text.find(c, end) for c in ".!?\n") if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return text[left + 1:right]


def find_instruction_text(text: str) -> list[PageFinding]:
    """Passages of ``text`` worded as instructions to an AI."""
    if not text:
        return []

    findings: list[PageFinding] = []
    seen: set[str] = set()
    for pattern, reason in _INSTRUCTION_PATTERNS:
        for m in pattern.finditer(text):
            f = _finding(KIND_INSTRUCTION_TEXT, f"text that {reason}", _sentence_around(text, m.start(), m.end()))
            if f.fingerprint not in seen:
                seen.add(f.fingerprint)
                findings.append(f)
            if len(findings) >= _MAX_FINDINGS:
                return findings
    return findings


def screen_fetched_page(raw_html: Optional[str], text: str) -> list[PageFinding]:
    """Everything about a fetched page the user should see before it is indexed.

    ``raw_html`` is None for a fetched PDF; its hidden text is removed by the
    PDF reader's own scrub (``pdf_hidden_text``), so only wording is checked.
    """
    findings = find_hidden_text(raw_html or "", text) + find_instruction_text(text)
    return findings[:_MAX_FINDINGS]
