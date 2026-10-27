"""Section selection: the chat model reads a turn's knowledge bases' table of
contents and names the section that governs the question.

Precise retrieval (:mod:`app.services.kb_retrieval`) can hand over the right
regulation's wrong section: the cross-encoder reads a neighbouring section as
the better match for the question's words. On the KB accuracy eval (Phase 3
after-run, 2026-10-26) that was the commonest cause of a wrong answer — in 82
of 190 incorrect answers no passage held any of the answer text, though every
answer sat in the bases as ingested — and the answer then applied the
neighbouring rule with a citation. The gold section was a sibling of one
handed over (§ 46.409 *Wards* for "kids in state custody", §§ 46.404–46.408
handed over), a section of another source of the same base (the plain-language
NIH summary instead of § 50.604), or one far from it; adding more of the
sections already handed over reached it rarely.

Given the bases' section numbers and titles, one per line, the chat model named
the governing section first for 25 of 50 such development questions and 9 of 16
held-out ones (within its three picks, 76% and 62%), and for 74 of 100 that
were answered right. So while the bases are searched, the model is asked once
for the section, and that section's best chunks join the passages after every
cap (:func:`app.services.kb_grounding.with_section`). Only its first pick is
used: all three added more than twice the passages for 1.4 times the answer
text. The call is made at temperature 0 and given ``TIMEOUT_S``; one
that fails, times out or names no section of these bases adds nothing.

Its weak spot is a big section: where the first pick was right, its best two
chunks held all the answer text in 9 of 10 sections of up to three chunks and
7 of 16 of nine or more.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import string
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are given the table of contents of one or more knowledge bases of regulations and institutional policies, "
    "and a question from a research administrator. Name the sections whose text most likely states the rule that "
    "answers the question: the section that governs the specific case the question describes, not a general, "
    "introductory or neighbouring one. A question in everyday words still has a governing section: map its "
    "words to the terms the regulation or policy itself uses. Reply with JSON only: "
    '{"sections": ["<id>", ...]} with 1 to 3 ids copied exactly from the table of contents, best first.'
)
# The eval's calls took a median 2.5 s, 4.0 s at the 90th percentile and 11.3 s
# at most, for a median 1,053 prompt and 283 completion tokens.
TIMEOUT_S = 10.0
MAX_TOKENS = 3000
CACHE_SIZE = 256
TITLE_MAX_CHARS = 110
# A source without section numbers is one line, with the sub-headings it covers.
COVERS_MAX = 10
COVER_MAX_CHARS = 60


@dataclass
class Contents:
    """One base's table of contents: its label in the prompt ("A", "B", …) and
    a line per section key, in the base's order."""
    label: str
    kb_uuid: str
    title: str
    lines: dict[str, str] = field(default_factory=dict)


def table_of_contents(index) -> dict[str, str]:
    """A line per section of a base (a ``kb_retrieval.KbIndex``), in its order:
    the section key and title, or for a source without section numbers its key,
    "(whole document)" and the sub-headings it covers. Sections that do not
    apply here (``index.excluded``) are left out."""
    lines: dict[str, str] = {}
    covers: dict[str, list[str]] = {}
    for i, key in enumerate(index.keys):
        if i in index.excluded:
            continue
        if key.startswith("source:"):
            lines.setdefault(key, f"{key} (whole document)")
            sub = (index.prefixes[i] or "").split(" — ", 1)
            seen = covers.setdefault(key, [])
            if len(sub) > 1 and sub[1][:COVER_MAX_CHARS] not in seen and len(seen) < COVERS_MAX:
                seen.append(sub[1][:COVER_MAX_CHARS])
        elif key not in lines:
            title = index.section_titles.get(key) or (index.chunks[i].get("metadata") or {}).get("section_title") or ""
            lines[key] = f"{key} — {str(title).strip()[:TITLE_MAX_CHARS]}"
    for key, seen in covers.items():
        if seen:
            lines[key] += " — covers: " + "; ".join(seen)
    return lines


def prompt(contents: list[Contents], question: str, previous: Optional[str] = None) -> str:
    """The user prompt: every base's lines under its label, then the question
    (and the one it follows)."""
    lines: list[str] = []
    for c in contents:
        lines.append(f"Knowledge base {c.label}: {c.title}")
        lines.extend(f"{c.label}|{line}" for line in c.lines.values())
    return ("Table of contents:\n" + "\n".join(lines) + f"\n\nQuestion: {question}"
            + (f"\n(The question follows this earlier question: {previous})" if previous else ""))


def parse(output: str) -> list[str]:
    """The section ids the model named, best first: the ``sections`` list of the
    first JSON object in its reply that has one."""
    text = re.sub(r"<think>.*?</think>", "", output or "", flags=re.S)
    decoder = json.JSONDecoder()
    at = text.find("{")
    while at >= 0:
        try:
            obj, _ = decoder.raw_decode(text[at:])
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("sections"), list):
            return [s for s in obj["sections"] if isinstance(s, str)][:3]
        at = text.find("{", at + 1)
    return []


def _forms(pick: str) -> list[str]:
    """A pick as written, without "(whole document)" or "covers: …", and cut at
    its title — a source name can hold " — " itself, so that is tried last."""
    p = pick.strip().lstrip("§").strip()
    out = [p, re.split(r" \(whole document\)| — covers:", p)[0].strip(), p.split(" — ")[0].strip()]
    return [f for n, f in enumerate(out) if f and f not in out[:n]]


def resolve(pick: str, contents: list[Contents]) -> Optional[tuple[str, str]]:
    """(kb_uuid, section key) of a pick: as labelled ("A|200.307"), or a key of
    any base when the label is missing or wrong; None when it is no section of
    these bases."""
    for form in _forms(pick):
        label, sep, key = form.partition("|")
        if sep:
            for c in contents:
                if label.strip() == c.label and key.strip() in c.lines:
                    return c.kb_uuid, key.strip()
        bare = key.strip() if sep else form
        for c in contents:
            if bare in c.lines:
                return c.kb_uuid, bare
    return None


_CACHE: "OrderedDict[tuple, Optional[tuple[str, str]]]" = OrderedDict()


async def pick(bases: list[tuple[str, str, object]], question: str, previous: Optional[str],
               model_name: Optional[str]) -> Optional[tuple[str, str]]:
    """(kb_uuid, section key) of the section ``model_name`` names first for
    ``question`` from the table of contents of ``bases`` — ``[(kb_uuid, title,
    index)]``; None without a model or a base, when the call fails or times out,
    or when its first pick is no section of these bases."""
    question = (question or "").strip()
    if not question or not model_name or not bases:
        return None
    contents = [Contents(string.ascii_uppercase[n % 26], kb_uuid, title or "", table_of_contents(index))
                for n, (kb_uuid, title, index) in enumerate(bases)]
    key = (model_name, question, previous or "", tuple((u, getattr(ix, "built_at", 0.0)) for u, _, ix in bases))
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    try:
        from app.services.kb_validation_service import _get_or_build_agent

        agent = _get_or_build_agent("kb_section_picker", model_name, SYSTEM_PROMPT,
                                    model_settings={"temperature": 0.0, "max_tokens": MAX_TOKENS})
        run = await asyncio.wait_for(agent.run(prompt(contents, question, previous)), timeout=TIMEOUT_S)
        picks = parse(str(run.output or ""))
    except Exception as e:  # noqa: BLE001 — the turn goes on without it
        logger.warning("KB section pick failed: %s", e)
        return None
    found = resolve(picks[0], contents) if picks else None
    _CACHE[key] = found
    while len(_CACHE) > CACHE_SIZE:
        _CACHE.popitem(last=False)
    return found
