"""An answer about attached documents is checked for a value the documents
give for something other than what was asked, and rewritten when the check
finds one — the check and rewrite the 2026-11-01 fresh held-out test
measured (the prime's 50% rate given as a subrecipient's)."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.services import chat_answer_repair
from app.services import chat_doc_answer_check as C
from app.services import chat_service
from app.services.doc_passages import DocumentContext

PAGES = [
    {"label": "budget_justification.pdf p. 1", "content": "Subaward to LoTek Institute: $270,000."},
    {"label": "budget_justification.pdf p. 3", "content": "F&A is charged at 50.00% of MTDC."},
]
QUESTION = "What indirect cost rate is LoTek using inside its subaward?"
ANSWER = "- **Indirect cost rate for the LoTek subaward:** 50.00% (p. 3)"
FIXED = ("- The documents do not state LoTek's own indirect cost rate.\n"
         "- 50.00% of MTDC is the University's rate on its own costs (p. 3).")
CONFIG = C.CheckConfig(checker="kimi", rewriter="kimi")


def _label(label="substituted", why="50% is the prime's rate on its own MTDC, not LoTek's."):
    return json.dumps({"label": label, "claim": "LoTek's rate is 50%", "why": why})


def _rewrite(answer=FIXED, verdict="rewritten"):
    return f"VERDICT: {verdict}\nANSWER:\n{answer}"


def _asker(replies, delays=None):
    """An ask that answers the check by "check" and the rewrite by "rewrite":
    a reply string, an exception to raise, or a list of them given in turn
    (the last one repeats). Records each call."""
    calls = []

    async def ask(model, instructions, prompt, max_tokens):
        role = "rewrite" if instructions == C.REWRITE_INSTRUCTIONS else "check"
        calls.append({"role": role, "model": model, "prompt": prompt, "max_tokens": max_tokens})
        await asyncio.sleep((delays or {}).get(role, 0))
        reply = replies[role]
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    ask.calls = calls
    return ask


# ------------------------------------------------------------------ setting

def test_the_step_is_off_unless_chat_config_turns_it_on():
    assert C.check_config(None) is None
    assert C.check_config({"chat_config": {}}) is None
    assert C.check_config({"chat_config": {"doc_answer_check_enabled": False}}) is None


def test_on_it_defaults_to_kimi_checking_and_rewriting():
    assert C.check_config({"chat_config": {"doc_answer_check_enabled": True}}) == C.CheckConfig(
        checker="moonshotai/kimi-k3", rewriter="moonshotai/kimi-k3")
    cfg = {"doc_answer_check_enabled": True, "doc_answer_check_model": "a", "doc_answer_rewrite_model": "b"}
    assert C.check_config({"chat_config": cfg}) == C.CheckConfig(checker="a", rewriter="b")


def test_the_prompts_are_the_studys():
    assert C.CHECK_INSTRUCTIONS.startswith("You check an answer from a research-administration assistant")
    assert '"substituted" | "not_stated" | "answered" | "other"' in C.CHECK_INSTRUCTIONS
    assert "A calculation the question asks for is an answer, not an assumption" in C.REWRITE_INSTRUCTIONS
    assert "when it does not hold, reply VERDICT: kept" in C.REWRITE_INSTRUCTIONS
    # v1's one-line calculation exception was replaced by the rule above.
    assert "a calculation from stated values is an answer, not an assumption" not in C.REWRITE_INSTRUCTIONS


def _scope(**over):
    args = dict(documents_whole=[True], document_chars=12000, knowledge_bases=False, other_attachments=False,
                low_quality=False, tool_results=[])
    return C.in_scope(**{**args, **over})


def test_only_whole_readable_attached_documents_with_nothing_else_are_in_scope():
    assert _scope()
    assert _scope(tool_results=[{"tool_name": "search_attached_documents"}])
    assert not _scope(documents_whole=[])
    assert not _scope(documents_whole=[True, False])
    assert not _scope(document_chars=C.MAX_DOCUMENT_CHARS + 1)
    assert not _scope(document_chars=0)
    assert not _scope(knowledge_bases=True)
    assert not _scope(other_attachments=True)
    assert not _scope(low_quality=True)
    for tool in ("search_documents", "get_document_text", "web_search", "fetch_url", "search_knowledge_base"):
        assert not _scope(tool_results=[{"tool_name": tool}]), tool


# -------------------------------------------------------------------- pages

def test_pages_are_cut_at_the_chats_page_positions_and_labelled_by_title():
    raw = "cover\nPage one text.\nPage two text."
    pages = C.document_pages("notice.pdf", raw, [(6, 1, False), (21, 2, True)])
    assert pages == [
        {"label": "notice.pdf before p. 1", "content": "cover"},
        {"label": "notice.pdf p. 1", "content": "Page one text."},
        {"label": "notice.pdf p. 2", "content": "Page two text."},
    ]


def test_a_workbook_is_cut_by_sheet_and_plain_text_is_one_page():
    raw = "Summary rows\nTravel rows"
    markers = [{"kind": "sheet", "value": "Travel", "char_offset": 13}, {"kind": "sheet", "value": "Summary",
                                                                         "char_offset": 0}]
    assert [p["label"] for p in C.document_pages("b.xlsx", raw, [], markers)] == ["b.xlsx sheet Summary",
                                                                                  "b.xlsx sheet Travel"]
    assert C.document_pages("t.txt", "  all  ", []) == [{"label": "t.txt whole", "content": "all"}]


def test_a_long_page_is_capped():
    (page,) = C.document_pages("x", "a" * (C.PAGE_CHARS + 50), [])
    assert len(page["content"]) == C.PAGE_CHARS


def test_the_checker_sees_the_question_every_page_and_the_answer():
    prompt = C.check_prompt(QUESTION, "Earlier?", PAGES, ANSWER)
    assert prompt.startswith(f"QUESTION: {QUESTION}\nEARLIER QUESTION IN THIS CONVERSATION: Earlier?\n")
    assert "ATTACHED DOCUMENTS, BY PAGE:\n[budget_justification.pdf p. 1]\nSubaward" in prompt
    assert "[budget_justification.pdf p. 3]\nF&A is charged at 50.00% of MTDC.\n" in prompt
    assert prompt.endswith(f"ANSWER:\n{ANSWER}")
    rw = C.rewrite_prompt(QUESTION, None, PAGES, ANSWER, "because")
    assert "EARLIER QUESTION" not in rw and rw.endswith(f"ANSWER:\n{ANSWER}\n\nCHECKER'S REASON: because")


# ------------------------------------------------------------------ parsing

def test_a_check_reply_is_read_past_think_blocks_and_code_fences():
    out = C.parse_check("<think>hm</think>```json\n" + _label("Substituted ") + "\n```")
    assert out["label"] == "substituted" and out["claim"] == "LoTek's rate is 50%"


@pytest.mark.parametrize("reply", ["no json", "[1, 2]", '{"claim": "x"}'])
def test_an_unreadable_check_reply_raises(reply):
    with pytest.raises(ValueError):
        C.parse_check(reply)


def test_a_rewrite_reply_gives_its_verdict_and_answer():
    assert C.parse_rewrite(_rewrite()) == ("rewritten", FIXED)
    assert C.parse_rewrite("ANSWER:\nx") == ("?", "x")
    with pytest.raises(ValueError):
        C.parse_rewrite("VERDICT: kept\nANSWER:\n  ")


# --------------------------------------------------------------------- step

async def test_a_substituted_answer_is_rewritten_with_the_checkers_reason():
    ask = _asker({"check": _label(), "rewrite": _rewrite()})
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, ask, prev_question="Before?")
    assert answer == FIXED
    assert rec["outcome"] == "repaired" and rec["kind"] == "attached_documents" and rec["original_answer"] == ANSWER
    assert rec["check"]["label"] == "substituted" and rec["pages"] == 2
    assert rec["rewrite"] == {"model": "kimi", "verdict": "rewritten", "unchanged": False,
                              "seconds": rec["rewrite"]["seconds"]}
    assert [c["role"] for c in ask.calls] == ["check", "rewrite"]
    assert [c["max_tokens"] for c in ask.calls] == [C.CHECK_MAX_TOKENS, C.REWRITE_MAX_TOKENS]
    assert ask.calls[1]["prompt"].endswith("CHECKER'S REASON: 50% is the prime's rate on its own MTDC, not LoTek's.")
    assert "EARLIER QUESTION IN THIS CONVERSATION: Before?" in ask.calls[1]["prompt"]


@pytest.mark.parametrize("label", ["answered", "not_stated", "other"])
async def test_any_other_label_keeps_the_answer_without_a_rewrite(label):
    ask = _asker({"check": _label(label)})
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == label
    assert "rewrite" not in rec and "original_answer" not in rec and len(ask.calls) == 1


async def test_a_label_outside_the_four_counts_as_other():
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, _asker({"check": _label("maybe")}))
    assert answer == ANSWER and rec["outcome"] == "other"


@pytest.mark.parametrize("reply", [_rewrite(ANSWER, "kept"), _rewrite("  " + ANSWER.replace(" ", "  ") + "\n")])
async def test_a_rewrite_that_changes_nothing_keeps_the_answer(reply):
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG,
                                            _asker({"check": _label(), "rewrite": reply}))
    assert answer == ANSWER and rec["outcome"] == "kept" and rec["rewrite"]["unchanged"] is True


async def test_a_failed_or_unreadable_check_is_asked_once_more_then_keeps_the_answer():
    ask = _asker({"check": [RuntimeError("429"), _label()], "rewrite": _rewrite()})
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, ask)
    assert answer == FIXED and rec["check"]["retried"].startswith("RuntimeError: 429")
    ask = _asker({"check": ["no json", "still none"]})
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "check_failed" and len(ask.calls) == 2


async def test_a_failed_rewrite_is_asked_once_more_then_keeps_the_answer():
    ask = _asker({"check": _label(), "rewrite": [RuntimeError("429"), _rewrite()]})
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG, ask)
    assert answer == FIXED and rec["rewrite"]["retried"].startswith("RuntimeError")
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG,
                                            _asker({"check": _label(), "rewrite": "no answer block"}))
    assert answer == ANSWER and rec["outcome"] == "rewrite_failed" and "error" in rec["rewrite"]


async def test_a_late_check_or_rewrite_keeps_the_answer(monkeypatch):
    monkeypatch.setattr(C, "CHECK_SECONDS", 0.05)
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG,
                                            _asker({"check": _label()}, delays={"check": 1}))
    assert answer == ANSWER and rec["outcome"] == "check_failed" and rec["check"]["error"] == "timed_out"
    monkeypatch.setattr(C, "CHECK_SECONDS", 5)
    monkeypatch.setattr(C, "REWRITE_SECONDS", 0.05)
    answer, rec = await C.check_and_rewrite(ANSWER, QUESTION, PAGES, CONFIG,
                                            _asker({"check": _label(), "rewrite": _rewrite()}, delays={"rewrite": 1}))
    assert answer == ANSWER and rec["outcome"] == "rewrite_failed" and rec["rewrite"]["error"] == "timed_out"


async def test_no_pages_or_no_answer_is_not_checked():
    ask = _asker({"check": _label()})
    assert (await C.check_and_rewrite(ANSWER, QUESTION, [], CONFIG, ask))[1]["outcome"] == "not_checked"
    assert (await C.check_and_rewrite(" ", QUESTION, PAGES, CONFIG, ask))[1]["outcome"] == "not_checked"
    assert ask.calls == []


# --------------------------------------------------------------- chat wiring

def _history(question):
    return [ModelRequest(parts=[UserPromptPart(content=question)]), ModelResponse(parts=[TextPart(content="An answer.")])]


def _doc(uuid="d1", raw="Intro\nF&A is charged at 50.00% of MTDC.", markers=None):
    return SimpleNamespace(uuid=uuid, title="bj.pdf", raw_text=raw, text_markers=markers)


async def test_chat_runs_the_step_only_when_on_and_on_a_whole_attached_document_answer(monkeypatch):
    seen = []

    async def fake(answer, question, pages, config, ask, *, prev_question=None):
        seen.append({"pages": pages, "prev": prev_question, "config": config})
        return "fixed", {"outcome": "repaired", "kind": "attached_documents"}

    monkeypatch.setattr(C, "check_and_rewrite", fake)
    monkeypatch.setattr(chat_answer_repair, "model_ask", lambda model, doc: None)
    on = {"chat_config": {"doc_answer_check_enabled": True}}
    whole = {"d1": DocumentContext(whole=True)}

    async def run(doc, docs=None, held=whole, kbs=False, other=False, lowq=False, tools=(), answer="a"):
        return await chat_service._check_document_answer(
            answer, "q", [_doc()] if docs is None else docs, held, kbs, other, lowq, list(tools),
            _history("Earlier?"), "m", doc)

    assert await run({}) == ("a", None)
    assert await run(on, docs=[]) == ("a", None)
    assert await run(on, held={"d1": DocumentContext(pages={1})}) == ("a", None)
    assert await run(on, held={}) == ("a", None)
    assert await run(on, kbs=True) == ("a", None)
    assert await run(on, other=True) == ("a", None)
    assert await run(on, lowq=True) == ("a", None)
    assert await run(on, tools=[{"tool_name": "search_documents"}]) == ("a", None)
    assert await run(on, docs=[_doc(raw="x" * (C.MAX_DOCUMENT_CHARS + 1))]) == ("a", None)
    assert await run(on, answer=" ") == (" ", None)
    assert seen == []
    assert await run(on) == ("fixed", {"outcome": "repaired", "kind": "attached_documents"})
    assert seen[0]["pages"] == [{"label": "bj.pdf whole", "content": "Intro\nF&A is charged at 50.00% of MTDC."}]
    assert seen[0]["prev"] == "Earlier?" and seen[0]["config"].checker == "moonshotai/kimi-k3"


async def test_chat_keeps_the_answer_when_the_step_raises(monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("bug")

    monkeypatch.setattr(C, "check_and_rewrite", boom)
    monkeypatch.setattr(chat_answer_repair, "model_ask", lambda model, doc: None)
    out = await chat_service._check_document_answer(
        "a", "q", [_doc()], {"d1": DocumentContext(whole=True)}, False, False, False, [], [], "m",
        {"chat_config": {"doc_answer_check_enabled": True}})
    assert out == ("a", None)
