"""Check a finished answer about attached documents for a value the
documents attach to something other than what was asked, and rewrite it
when they do.

The model answering about attached documents rarely misquotes a page. It
answers a question the documents leave open with a value they give for
something else: another award's amount, the prime's rate applied to a
subrecipient, a line total read as a per-unit price, an allowed range read
as a reading. Rules in the answering prompt did not change that on held-out
items (2026-10-31). A check after the answer did (probes of 2026-10-31 and
2026-11-01, reports doc-chat-checkprobe-2026-10-31 and
doc-chat-fresh-heldout-2026-11-01). Here, when
``chat_config["doc_answer_check_enabled"]`` is on (it is off by default):

1. One checker (kimi-k3, temperature 0, thinking off) reads the question,
   every page of the attached documents and the answer, and labels the
   answer "substituted", "not_stated", "answered" or "other". On fresh
   items it flagged 139 of 168 unsupported answers, no correct abstention,
   and 14 of 204 correct answers, all of them calculations.
2. A "substituted" answer goes to the rewriter (the same model), with the
   checker's reason. It either says the documents do not state what was
   asked and gives the nearby values as what they are, or keeps the answer
   when the reason does not hold. Its rule for calculations kept all 14
   wrongly flagged answers correct.
3. Any other label, a late or failed call, a reply that cannot be read, or
   a rewrite that changes nothing keeps the answer as it was.

It runs only on the turns it was measured on: attached documents, every
page of them sent to the model, together under ``MAX_DOCUMENT_CHARS``, with
no knowledge base, URL or file attachment, and no tool beyond the attached
documents' own search. Every step is recorded on the message
(``answer_check``, ``kind: "attached_documents"``), with the original answer
when it was replaced.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from app.services.chat_answer_repair import Ask, parse_json

logger = logging.getLogger(__name__)

VERSION = 1
KIND = "attached_documents"
DEFAULT_CHECKER = "moonshotai/kimi-k3"
CHECK_SECONDS = 20.0          # 4.1 s median, 6.5 s p90 under parallel load in the study
REWRITE_SECONDS = 30.0        # 6.1 s median, 9.2 s p90
CHECK_MAX_TOKENS = 6000
REWRITE_MAX_TOKENS = 4000
PAGE_CHARS = 16000            # of one page shown to the checker and the rewriter
MAX_DOCUMENT_CHARS = 45000    # the attached text the study checked, all documents together

# The only tool whose results come from the attached documents themselves.
DOCUMENT_TOOLS = frozenset({"search_attached_documents"})

# The study's checker prompt (checkprobe.py INSTR_B), word for word.
CHECK_INSTRUCTIONS = """You check an answer from a research-administration assistant to a question about documents the user attached (award notices, budgets, subawards, proposals, invoices). Research administrators act on these answers, so presenting the wrong value as the answer is a serious error.

Decide one thing: does the answer present, as the answer to the question, something the documents do not state for what the question asks?

Label the answer:
- "substituted": the answer's main claim gives a value, name, date, rate or yes/no that the documents attach to something other than what was asked (a different award, amendment, budget period or year, party, person, line, category or section); or applies a general rate, term or rule to a case the documents do not address; or gives a figure worked out from an assumption the documents do not state (an even split, a per-unit price from a total); or gives a value from general knowledge.
- "not_stated": the answer says the documents do not state what was asked. It may still give nearby values, as long as it says what they are.
- "answered": the documents state what was asked and the answer gives it as they state it.
- "other": none of these fits (the answer is wrong in another way, or makes no claim).

Judge only against the documents; do not use your own knowledge. Do not judge style, length or citations.

Return ONLY a JSON object: {"label": "substituted" | "not_stated" | "answered" | "other", "claim": "<the answer's main claim, short>", "why": "<what the documents attach that value to, or where they state the answer; under 40 words>"}"""

# The study's rewrite prompt v2 (v2probe.py REWRITE_INSTR2), word for word.
REWRITE_INSTRUCTIONS = """You correct an answer from a research-administration assistant to a question about documents the user attached. Research administrators act on these answers. A checker read the answer against the documents and flagged it: it says the answer presents, as the answer to the question, something the documents do not state for what was asked. The checker can be wrong.

Read the question, the documents and the checker's reason.
- If the checker is right, rewrite the answer: say first, plainly, that the documents do not state what was asked; then give the nearest values the documents do state, each as what the documents attach it to (its award, period, party, line or section), with its page. Do not compute a figure from an assumption (an even split, a per-unit price from a total) and do not use general knowledge.
- If the documents do state what was asked and the answer gives it, keep the answer unchanged.

A calculation the question asks for is an answer, not an assumption: a sum, a difference, a remaining balance, a share or percentage, an average (what an amount "works out to" per person or item), or a unit price on a line that states both the quantity and the amount, computed from values the documents state. When its inputs are stated and its arithmetic is right, it answers the question. It is an assumption only when it needs a value the documents don't give (a count, a number of periods or units), or when the question asks what one person, period or unit actually gets or is charged and the documents give only a total: dividing then assumes equal shares the documents don't state. Check the checker's reason against the documents before you rewrite: when it does not hold, reply VERDICT: kept and repeat the answer unchanged.

Keep the answer short, in the same format (markdown bullets), with page citations like (p. 3). Judge only against the documents.

Reply in exactly this format:
VERDICT: rewritten | kept
ANSWER:
<the full answer>"""

LABELS = ("substituted", "not_stated", "answered", "other")


@dataclass(frozen=True)
class CheckConfig:
    checker: str
    rewriter: str


def check_config(sys_config_doc: Optional[dict]) -> Optional[CheckConfig]:
    """The settings in ``chat_config``, or None when the step is off.

    Keys: ``doc_answer_check_enabled`` (default False),
    ``doc_answer_check_model`` (default kimi-k3) and
    ``doc_answer_rewrite_model`` (default: the checker)."""
    cfg = (sys_config_doc or {}).get("chat_config") or {}
    if not bool(cfg.get("doc_answer_check_enabled", False)):
        return None
    checker = str(cfg.get("doc_answer_check_model") or DEFAULT_CHECKER)
    return CheckConfig(checker=checker, rewriter=str(cfg.get("doc_answer_rewrite_model") or checker))


def in_scope(
    *, documents_whole: list[bool], document_chars: int, knowledge_bases: bool,
    other_attachments: bool, low_quality: bool, tool_results: list[dict],
) -> bool:
    """Whether a turn is one the check was measured on: attached documents,
    each sent to the model whole and together under ``MAX_DOCUMENT_CHARS``,
    readable, with nothing else in context and no tool beyond the attached
    documents' own search. The checker sees only those documents, so a value
    the answer took from anywhere else would read as substituted."""
    return (
        bool(documents_whole) and all(documents_whole)
        and 0 < document_chars <= MAX_DOCUMENT_CHARS
        and not knowledge_bases and not other_attachments and not low_quality
        and all(r.get("tool_name") in DOCUMENT_TOOLS for r in tool_results or [])
    )


# ------------------------------------------------------------------ pages

def document_pages(title: str, raw_text: str, page_positions: list[tuple[int, int, bool]],
                   markers: Optional[list[dict]] = None) -> list[dict]:
    """A document's pages (or sheets) as the checker reads them: one
    ``{label, content}`` each, labelled "<title> p. N", in page order.

    ``page_positions`` are ``(offset, page, approximate)`` as the chat finds
    them in the stored text. A workbook has none, and is split by its sheet
    markers; a text with neither is one page."""
    raw = raw_text or ""
    if page_positions:
        spans = []
        for i, (off, page, _approx) in enumerate(page_positions):
            end = page_positions[i + 1][0] if i + 1 < len(page_positions) else len(raw)
            spans.append((f"p. {page}", raw[off:end]))
        if page_positions[0][0] > 0:
            spans.insert(0, ("before p. 1", raw[:page_positions[0][0]]))
    else:
        sheets = sorted((m["char_offset"], m["value"]) for m in markers or []
                        if isinstance(m, dict) and m.get("kind") == "sheet")
        if sheets:
            spans = [(f"sheet {name}", raw[off:(sheets[i + 1][0] if i + 1 < len(sheets) else len(raw))])
                     for i, (off, name) in enumerate(sheets)]
        else:
            spans = [("whole", raw)]
    return [{"label": f"{title} {lab}", "content": text.strip()[:PAGE_CHARS]} for lab, text in spans]


def _heading(question: str, prev_question: Optional[str], pages: list[dict]) -> list[str]:
    lines = [f"QUESTION: {question}"]
    if prev_question:
        lines.append(f"EARLIER QUESTION IN THIS CONVERSATION: {prev_question}")
    lines.append("\nATTACHED DOCUMENTS, BY PAGE:")
    lines += [f"[{p['label']}]\n{p['content']}\n" for p in pages]
    return lines


def check_prompt(question: str, prev_question: Optional[str], pages: list[dict], answer: str) -> str:
    return "\n".join([*_heading(question, prev_question, pages), f"ANSWER:\n{answer}"])


def rewrite_prompt(question: str, prev_question: Optional[str], pages: list[dict], answer: str, why: str) -> str:
    return "\n".join([*_heading(question, prev_question, pages), f"ANSWER:\n{answer}", f"\nCHECKER'S REASON: {why}"])


# ---------------------------------------------------------------- parsing

def parse_check(text: str) -> dict:
    """``{label, claim, why}`` from the checker's reply."""
    obj = parse_json(text)
    if not isinstance(obj, dict) or "label" not in obj:
        raise ValueError("checker reply has no label")
    return {"label": str(obj["label"]).strip().lower(), "claim": str(obj.get("claim") or "")[:300],
            "why": str(obj.get("why") or "")[:500]}


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_ANSWER_RE = re.compile(r"^\s*ANSWER:\s*\n?(.*)\Z", re.S | re.M)
_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(\w+)", re.M)


def parse_rewrite(text: str) -> tuple[str, str]:
    """``(verdict, answer)`` from the rewriter's reply."""
    t = _THINK_RE.sub("", text or "")
    m = _ANSWER_RE.search(t)
    if not m or not m.group(1).strip():
        raise ValueError(f"no ANSWER block: {t[:200]!r}")
    v = _VERDICT_RE.search(t)
    return (v.group(1).lower() if v else "?"), m.group(1).strip()


def _same(a: str, b: str) -> bool:
    return " ".join((a or "").split()) == " ".join((b or "").split())


# ------------------------------------------------------------------- step

async def _ask_twice(ask: Ask, model: str, instructions: str, prompt: str, max_tokens: int, parse, rec: dict):
    """A failed call or an unreadable reply is asked for once more, as the
    study's probe did; ``retried`` keeps why."""
    try:
        return parse(await ask(model, instructions, prompt, max_tokens))
    except Exception as e:  # noqa: BLE001
        rec["retried"] = f"{type(e).__name__}: {e}"[:300]
    return parse(await ask(model, instructions, prompt, max_tokens))


async def check_and_rewrite(
    answer: str, question: str, pages: list[dict], config: CheckConfig, ask: Ask,
    *, prev_question: Optional[str] = None,
) -> tuple[str, dict]:
    """``(answer to keep, record)``. The answer is the rewritten one only
    when the checker labelled it "substituted" and the rewrite changed it;
    ``record["outcome"]`` says which step settled it ("repaired" when the
    answer was replaced, as for the knowledge-base repair)."""
    started = time.monotonic()
    record: dict = {"version": VERSION, "kind": KIND, "pages": len(pages)}

    def done(outcome: str, final: str = answer) -> tuple[str, dict]:
        record["outcome"] = outcome
        record["seconds"] = round(time.monotonic() - started, 2)
        return final, record

    if not pages or not answer.strip():
        return done("not_checked")

    check: dict = {"model": config.checker}
    record["check"] = check
    at = time.monotonic()
    try:
        out = await asyncio.wait_for(
            _ask_twice(ask, config.checker, CHECK_INSTRUCTIONS, check_prompt(question, prev_question, pages, answer),
                       CHECK_MAX_TOKENS, parse_check, check),
            CHECK_SECONDS,
        )
        check.update(out)
    except asyncio.TimeoutError:
        check["error"] = "timed_out"
    except Exception as e:  # noqa: BLE001 — a failed check changes nothing
        logger.warning("Attached-document answer check by %s failed: %s", config.checker, e)
        check["error"] = f"{type(e).__name__}: {e}"[:300]
    check["seconds"] = round(time.monotonic() - at, 2)
    if check.get("error"):
        return done("check_failed")
    if check["label"] != "substituted":
        return done(check["label"] if check["label"] in LABELS else "other")

    rewrite: dict = {"model": config.rewriter}
    record["rewrite"] = rewrite
    at = time.monotonic()
    try:
        verdict, fixed = await asyncio.wait_for(
            _ask_twice(ask, config.rewriter, REWRITE_INSTRUCTIONS,
                       rewrite_prompt(question, prev_question, pages, answer, check.get("why") or ""),
                       REWRITE_MAX_TOKENS, parse_rewrite, rewrite),
            REWRITE_SECONDS,
        )
    except asyncio.TimeoutError:
        rewrite.update(error="timed_out", seconds=round(time.monotonic() - at, 2))
        return done("rewrite_failed")
    except Exception as e:  # noqa: BLE001 — a failed rewrite keeps the answer
        logger.warning("Attached-document answer rewrite by %s failed: %s", config.rewriter, e)
        rewrite.update(error=f"{type(e).__name__}: {e}"[:300], seconds=round(time.monotonic() - at, 2))
        return done("rewrite_failed")
    unchanged = _same(fixed, answer)
    rewrite.update(verdict=verdict, unchanged=unchanged, seconds=round(time.monotonic() - at, 2))
    if unchanged:
        return done("kept")
    record["original_answer"] = answer
    return done("repaired", fixed)
