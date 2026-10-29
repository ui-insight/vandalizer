"""Check a finished knowledge-base chat answer against every passage the
model was given, and rewrite the sentences that misstate one.

Most wrong KB answers whose deciding passage did reach the model misread it:
"should" becomes "must", an exception is added that the passages do not
give, a conclusion is reversed (error study of 2026-10-28, records commit
ef3a7e2). The per-claim check (``chat_claim_check``) marks such a claim's
chip, but it reads only the passages a claim cites and changes nothing.
Here, when ``chat_config["answer_repair_enabled"]`` is on (it is off by
default):

1. Two checkers label each sentence of the answer ok / contradicted /
   unsupported against ALL the passages the model was given, at the same
   time: a fast one (qwen3.5-122b with thinking off, about 2 s) and a slow
   one (kimi-k3), whose check is cut off 15 s after both start.
2. The answer is repaired only when both flag a sentence as contradicted
   (any sentence each). The fast model rewrites the sentences it flagged,
   given its reasons, and keeps the rest. Repairing on the fast checker's
   flags alone gained as much but broke four to six times as many correct
   answers. When the fast checker flags nothing, the slow one is not
   waited for.
3. A repair that changes nothing, a late or failed call, or a reply that
   cannot be read keeps the answer as it was.

A checker or repairer named here but not configured in System Config is
called on the answering model's endpoint, with its key, as the study called
them. Every step is recorded on the message (``answer_check``), with the
original answer when it was replaced, so a turn can be inspected and graded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

VERSION = 1
DEFAULT_CHECKER = "qwen/qwen3.5-122b"
DEFAULT_SECOND_CHECKER = "moonshotai/kimi-k3"
SECOND_CHECK_SECONDS = 15.0   # the slow checker's cap, from when both checks start
CHECK_SECONDS = 15.0          # the fast checker's: 2.0 s median, 3.8 s p90 in the study
REPAIR_SECONDS = 30.0         # check and repair on a flagged turn: 5.0 s median, 9.2 s p90
CHECK_MAX_TOKENS = 6000
REPAIR_MAX_TOKENS = 8000
PASSAGE_CHARS = 3000          # of a passage shown to the checker and the repairer

# The tools a measured KB turn ran. A turn that read attached documents, the
# web or anything else answers from text the checkers are not shown.
KB_TOOLS = frozenset({"search_knowledge_base", "list_knowledge_bases"})

# The study's checker prompt (probe.py), word for word.
CHECK_INSTRUCTIONS = """You check an assistant's answer against the knowledge-base passages it was given. Research administrators act on these answers, so a sentence that misstates a passage is a serious error.

For each numbered answer sentence, compare it with ALL the passages, not only the ones it cites, and label it:
- "contradicted": a passage says something incompatible with the sentence. For example: must / shall / should / may changed into another; a condition, limit or exception the passage attaches is dropped, so the rule reads broader or narrower than the passage; an exception, approval route, condition or option is added that the passages do not give; the rule is reversed (yes / no, is / is not, required / not required); a wrong number, date or threshold; two separate rules (for example different lettered paragraphs or list items) merged, so the terms of one are applied to the other; the wrong subject or scope.
- "unsupported": no passage states it, and no passage contradicts it.
- "ok": a passage states it, or the sentence makes no claim (a heading, transition or offer to help).

Judge only against the passages; do not use your own knowledge of the regulations. Do not mark a sentence for wording, style or brevity, or because it leaves out details the question did not ask about.

Return ONLY a JSON object:
{"sentences": [{"n": 1, "label": "ok" | "contradicted" | "unsupported", "passage": <P number or null>, "why": "<short reason; for contradicted, quote the conflicting passage words>"}]}"""

# The study's v1 repair prompt (repair.py), word for word. The tighter v2 did
# not help.
REPAIR_INSTRUCTIONS = """You correct an assistant's answer for research administrators, who act on it. A checker compared each numbered sentence of the answer with the knowledge-base passages the assistant was given, and flagged some sentences as contradicting a passage. The checker can be wrong.

For each flagged sentence, read the passage the checker names, and the other passages:
- If a passage does contradict the sentence, rewrite the sentence so it says what the passage says: keep the passage's must / shall / should / may, its conditions, limits and exceptions, its numbers and its scope. Do not add an exception, approval route or option the passages do not give. Do not merge separate rules (for example different lettered paragraphs or list items).
- If the passages support the sentence as written, keep it unchanged.

If a correction changes the answer's conclusion, also correct the opening or summary sentences that state it, so the answer does not contradict itself. If, once corrected, the passages do not settle the question, say so plainly. Keep every other sentence as written unless it repeats a point you corrected. Keep the answer's format (markdown, bullets) and its [Source: <label>] citations; cite with the passage labels given. Judge only against the passages; do not use your own knowledge of the regulations.

Reply in exactly this format:
CHANGED: <numbers of the sentences you rewrote, comma-separated, or none>
KEPT: <numbers of flagged sentences you kept because the checker was wrong, or none>
ANSWER:
<the full corrected answer>"""


@dataclass(frozen=True)
class RepairConfig:
    checker: str
    second_checker: Optional[str]   # None: repair on the first checker's flags alone
    repairer: str
    second_check_seconds: float = SECOND_CHECK_SECONDS


def repair_config(sys_config_doc: Optional[dict]) -> Optional[RepairConfig]:
    """The check-and-repair settings in ``chat_config``, or None when it is off.

    Keys: ``answer_repair_enabled`` (default False),
    ``answer_repair_checker_model`` (default qwen3.5-122b),
    ``answer_repair_second_checker_model`` (default kimi-k3; empty for none),
    ``answer_repair_model`` (default: the first checker) and
    ``answer_repair_second_check_seconds`` (default 15)."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    if not bool(cfg.get("answer_repair_enabled", False)):
        return None
    checker = str(cfg.get("answer_repair_checker_model") or DEFAULT_CHECKER)
    second = cfg.get("answer_repair_second_checker_model", DEFAULT_SECOND_CHECKER)
    try:
        cap = float(cfg.get("answer_repair_second_check_seconds") or SECOND_CHECK_SECONDS)
    except (TypeError, ValueError):
        cap = SECOND_CHECK_SECONDS
    return RepairConfig(
        checker=checker,
        second_checker=str(second) if second else None,
        repairer=str(cfg.get("answer_repair_model") or checker),
        second_check_seconds=cap if cap > 0 else SECOND_CHECK_SECONDS,
    )


def in_scope(tool_results: list[dict], *, attached_documents: bool) -> bool:
    """Whether a turn is one the check was measured on: a KB answer with no
    attached documents and no tools beyond the KB's own."""
    return not attached_documents and all(r.get("tool_name") in KB_TOOLS for r in tool_results or [])


# ------------------------------------------------------------------ passages

_TRANS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "‑": "-", " ": " ", " ": " ", " ": " ",
})
_PAGE_MARK_RE = re.compile(r"\[p\.\s*~?\d+\]")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANS)
    text = _PAGE_MARK_RE.sub(" ", text)
    text = re.sub(r"[*_`#>|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _tool_passages(content) -> list[dict]:
    """The passages a search_knowledge_base result gave the model, its lead-in
    already written into the text."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return []
    if isinstance(content, dict):
        content = content.get("results") or content.get("passages") or [content]
    if not isinstance(content, list):
        return []
    return [{"label": e.get("label") or e.get("source_name"), "content": e["content"], "lead_in": None}
            for e in content if isinstance(e, dict) and e.get("content")]


def seen_passages(prefetch: list[dict], tool_results: list[dict]) -> list[dict]:
    """The passages the model was given this turn, in the order it was given
    them, each once: the pre-fetched snippets (with the lead-in of a list a
    snippet opens inside), then what its own KB searches returned."""
    found = [{"label": s.get("label") or s.get("cite_label"), "content": s.get("content") or "",
              "lead_in": s.get("lead_in")} for s in prefetch or []]
    for r in tool_results or []:
        if r.get("tool_name") == "search_knowledge_base":
            found.extend(_tool_passages(r.get("content")))
    out, seen = [], set()
    for p in found:
        key = _norm(p["content"])[:300]
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


# ----------------------------------------------------------------- sentences

CITE_RE = re.compile(r"\[(?:Source:\s*)?([^\[\]]{3,300})\]")


def split_answer(answer: str) -> list[str]:
    """The answer's sentences, as the study's grader numbers them: each keeps
    the citation brackets it ends with."""
    out: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(*])|\n+", answer or ""):
        s = part.strip()
        if not s:
            continue
        if out and re.fullmatch(r"(\s*\[[^\]]+\]\s*)+[.;,]?", s):
            out[-1] += " " + s
            continue
        if len(re.sub(r"\W", "", CITE_RE.sub("", s))) < 10:
            continue
        out.append(s)
    return out


def _norm_label(s: Optional[str]) -> str:
    return _norm(re.sub(r"^\s*source:\s*", "", s or "", flags=re.I))


def cited_ids(sentence: str, passages: list[dict]) -> list[int]:
    """The P numbers (from 1) of the passages a sentence's citations name."""
    ids: set[int] = set()
    labels = [_norm_label(p.get("label")) for p in passages]
    for m in CITE_RE.finditer(sentence):
        for piece in re.split(r"\s*;\s*", _norm_label(m.group(1))):
            for i, pl in enumerate(labels):
                if pl and (piece == pl or (len(piece) > 12 and (piece in pl or pl in piece))):
                    ids.add(i + 1)
    return sorted(ids)


def _cites(ids: list[int]) -> str:
    return ", ".join(f"P{i}" for i in ids) if ids else "nothing"


def _heading(question: str, prev_question: Optional[str], passages: list[dict], *, label_prefix: str) -> list[str]:
    lines = [f"QUESTION: {question}"]
    if prev_question:
        lines.append(f"EARLIER QUESTION IN THIS CONVERSATION: {prev_question}")
    lines.append("\nPASSAGES THE ASSISTANT WAS GIVEN:" + (" (none)" if not passages else ""))
    for i, p in enumerate(passages, 1):
        lead = f"[Lead-in, earlier in this section: {p['lead_in']}]\n" if p.get("lead_in") else ""
        lines.append(f"[P{i}] {label_prefix}{p.get('label') or ''}\n{lead}{(p.get('content') or '')[:PASSAGE_CHARS]}\n")
    return lines


def _numbered(sents: list[tuple[str, list[int]]]) -> list[str]:
    return [f"S{n} (cites {_cites(ids)}): {CITE_RE.sub('', s).strip()}" for n, (s, ids) in enumerate(sents, 1)]


def check_prompt(question: str, prev_question: Optional[str], passages: list[dict],
                 sents: list[tuple[str, list[int]]]) -> str:
    return "\n".join([*_heading(question, prev_question, passages, label_prefix=""),
                      "ANSWER SENTENCES:", *_numbered(sents)])


def repair_prompt(question: str, prev_question: Optional[str], passages: list[dict], answer: str,
                  sents: list[tuple[str, list[int]]], flags: list[dict]) -> str:
    lines = [*_heading(question, prev_question, passages, label_prefix="label: "),
             f"ANSWER:\n{answer}\n", "ANSWER SENTENCES:", *_numbered(sents), "\nCHECKER FLAGS:"]
    for f in flags:
        lines.append(f"S{f['n']} contradicted" + (f" by P{f['passage']}" if f.get("passage") else "")
                     + f": {f.get('why') or ''}")
    return "\n".join(lines)


# ------------------------------------------------------------------- parsing

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def parse_json(text: str):
    """The first JSON value in a reply, past any think block or code fence."""
    t = _THINK_RE.sub("", text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1)
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON in reply")
    obj, _ = json.JSONDecoder().raw_decode(t[start:])
    return obj


def _passage_number(v) -> Optional[int]:
    """3 for 3, "3" or "P3"; None for anything else."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    m = re.fullmatch(r"\s*P?(\d+)\s*", v) if isinstance(v, str) else None
    return int(m.group(1)) if m else None


def parse_check(text: str) -> list[dict]:
    """A checker's labels, one per sentence it read: ``{n, label, passage, why}``."""
    obj = parse_json(text)
    if not isinstance(obj, dict):
        raise ValueError("checker reply is not a JSON object")
    items = obj.get("sentences") or []
    if not isinstance(items, list):
        raise ValueError("checker reply has no sentence list")
    out = []
    for s in items:
        if not isinstance(s, dict):
            continue
        n = s.get("n")
        out.append({
            "n": n if isinstance(n, int) and not isinstance(n, bool) else None,
            "label": str(s.get("label") or "").strip().lower(),
            "passage": _passage_number(s.get("passage")),
            "why": str(s.get("why") or "")[:1000],
        })
    return out


def contradicted(labels: list[dict], n_sentences: int) -> list[dict]:
    """The sentences a checker flagged as contradicting a passage."""
    return [s for s in labels if s["label"] == "contradicted" and s["n"] is not None and 1 <= s["n"] <= n_sentences]


_ANSWER_RE = re.compile(r"^\s*ANSWER:\s*\n?(.*)\Z", re.S | re.M)


def parse_repair(text: str, passages: list[dict]) -> tuple[str, list[int], list[int]]:
    """``(answer, changed, kept)`` from a repair reply, the answer cleaned."""
    t = _THINK_RE.sub("", text or "")
    m = _ANSWER_RE.search(t)
    if not m or not m.group(1).strip():
        raise ValueError(f"no ANSWER block: {t[:200]!r}")

    def nums(tag: str) -> list[int]:
        line = re.search(rf"^\s*{tag}:(.*)$", t, re.M)
        return [int(x) for x in re.findall(r"\d+", line.group(1))] if line else []

    return clean(m.group(1).strip(), passages), nums("CHANGED"), nums("KEPT")


_HYPHENS_RE = re.compile("[‐‑‒–]")


def clean(answer: str, passages: list[dict]) -> str:
    """Put a repaired answer back in the app's form: the model sometimes
    copies the prompt's "S2 (cites P4):" sentence prefixes, cites passages as
    [P3] or [Source: P3], and retypes labels with non-breaking hyphens."""
    def unprefix(mm: re.Match) -> str:  # "- **S2** (cites P4, P5): text" → "- text [P4, P5]", made a cite below
        ids = re.findall(r"P(\d+)", mm.group(2) or "")
        return mm.group(1) + mm.group(3).rstrip() + (f" [P{', P'.join(ids)}]" if ids else "")
    answer = re.sub(r"^(\W*?)\**S\d+\**\s*\((cites[^)]*|no citation)\)\s*:?\s*(.*)$", unprefix, answer, flags=re.M)

    def by_number(mm: re.Match) -> str:  # [P3] / [P3, P4] / [Source: P3; P4] → [Source: <label>]
        ids = [int(x) for x in re.findall(r"\d+", mm.group(0))]
        return " ".join(f"[Source: {passages[i - 1].get('label')}]" for i in ids if 1 <= i <= len(passages))
    answer = re.sub(r"\[(?:Source:\s*)?P\d+(?:\s*[,;]\s*P?\d+)*\]", by_number, answer)

    def hy(s: str) -> str:
        return _HYPHENS_RE.sub("-", s).strip()
    true = {hy(p.get("label") or ""): p.get("label") for p in passages if p.get("label")}

    def snap(mm: re.Match) -> str:  # a label retyped with other hyphens: the passage's own label
        pieces = [true.get(hy(x), x.strip()) for x in re.split(r"\s*;\s*", mm.group(1))]
        return "[Source: " + "; ".join(pieces) + "]"
    return re.sub(r"\[Source:\s*([^\[\]]{3,600})\]", snap, answer)


# ------------------------------------------------------------------ the step

# (model, instructions, prompt, max_tokens) → the reply's text
Ask = Callable[[str, str, str, int], Awaitable[str]]


async def _check(ask: Ask, model: str, prompt: str, n_sentences: int, timeout: float) -> dict:
    started = time.monotonic()
    rec: dict = {"model": model}
    try:
        labels = parse_check(await asyncio.wait_for(ask(model, CHECK_INSTRUCTIONS, prompt, CHECK_MAX_TOKENS), timeout))
        rec.update(labels=labels, flagged=[s["n"] for s in contradicted(labels, n_sentences)])
    except asyncio.TimeoutError:
        rec["error"] = "timed_out"
    except Exception as e:  # noqa: BLE001 — a failed check repairs nothing
        logger.warning("Answer check by %s failed: %s", model, e)
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    rec["seconds"] = round(time.monotonic() - started, 2)
    return rec


async def check_and_repair(
    answer: str, question: str, passages: list[dict], config: RepairConfig, ask: Ask,
    *, prev_question: Optional[str] = None,
) -> tuple[str, dict]:
    """``(answer to keep, record)``. The answer is the repaired one only when
    both checkers flagged it and the repair changed it; ``record["outcome"]``
    says which step settled it."""
    started = time.monotonic()
    sents = [(s, cited_ids(s, passages)) for s in split_answer(answer)]
    record: dict = {"version": VERSION, "sentences": [s for s, _ in sents], "passages": len(passages), "checks": []}

    def done(outcome: str, final: str = answer) -> tuple[str, dict]:
        record["outcome"] = outcome
        record["seconds"] = round(time.monotonic() - started, 2)
        return final, record

    if not sents or not passages:
        return done("not_checked")
    prompt = check_prompt(question, prev_question, passages, sents)
    first = asyncio.create_task(_check(ask, config.checker, prompt, len(sents), CHECK_SECONDS))
    second = (asyncio.create_task(_check(ask, config.second_checker, prompt, len(sents), config.second_check_seconds))
              if config.second_checker else None)
    try:
        r1 = await first
        record["checks"].append(r1)
        if r1.get("error") or not r1["flagged"]:
            if second is not None:
                record["checks"].append(
                    second.result() if second.done() else {"model": config.second_checker, "cancelled": True}
                )
            return done("check_failed" if r1.get("error") else "no_flags")
        if second is not None:
            r2 = await second
            record["checks"].append(r2)
            if r2.get("error"):
                return done("second_check_late" if r2["error"] == "timed_out" else "second_check_failed")
            if not r2["flagged"]:
                return done("second_check_no_flags")
    finally:
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()

    flags = contradicted(r1["labels"], len(sents))
    repair: dict = {"model": config.repairer, "flagged": [f["n"] for f in flags]}
    record["repair"] = repair
    at = time.monotonic()
    try:
        reply = await asyncio.wait_for(
            ask(config.repairer, REPAIR_INSTRUCTIONS,
                repair_prompt(question, prev_question, passages, answer, sents, flags), REPAIR_MAX_TOKENS),
            REPAIR_SECONDS,
        )
        fixed, changed, kept = parse_repair(reply, passages)
    except asyncio.TimeoutError:
        repair.update(error="timed_out", seconds=round(time.monotonic() - at, 2))
        return done("repair_failed")
    except Exception as e:  # noqa: BLE001 — a failed repair keeps the answer
        logger.warning("Answer repair by %s failed: %s", config.repairer, e)
        repair.update(error=f"{type(e).__name__}: {e}"[:300], seconds=round(time.monotonic() - at, 2))
        return done("repair_failed")
    unchanged = not changed or fixed.strip() == answer.strip()
    repair.update(changed=changed, kept=kept, unchanged=unchanged, seconds=round(time.monotonic() - at, 2))
    if unchanged:
        return done("unchanged")
    record["original_answer"] = answer
    return done("repaired", fixed)


def _with_model(model: str, answer_model: str, system_config_doc: Optional[dict]) -> dict:
    """``system_config_doc`` with ``model`` in it: as configured, else on the
    answering model's endpoint, with its key and protocol."""
    doc = system_config_doc or {}
    models = doc.get("available_models") or []
    if any(m.get("name") == model for m in models):
        return doc
    base = next((m for m in models if m.get("name") == answer_model), None)
    if base is None:
        return doc
    entry = {k: v for k, v in base.items() if k != "id"}
    return {**doc, "available_models": [*models, {**entry, "name": model}]}


def model_ask(answer_model: str, system_config_doc: Optional[dict]) -> Ask:
    """One temperature-0 call with thinking off, as the study made them,
    awaited on the chat's event loop (and metered with the chat's tokens)."""
    async def ask(model: str, instructions: str, prompt: str, max_tokens: int) -> str:
        from pydantic_ai import Agent

        from app.services.llm_service import build_thinking_model_settings, get_agent_model

        doc = _with_model(model, answer_model, system_config_doc)
        agent_model = get_agent_model(model, thinking_override=False, system_config_doc=doc)
        settings = dict(build_thinking_model_settings(model, False, doc) or {})
        settings.update(temperature=0.0, max_tokens=max_tokens)
        result = await Agent(agent_model, instructions=instructions, model_settings=settings).run(prompt)
        return result.output or ""

    return ask
