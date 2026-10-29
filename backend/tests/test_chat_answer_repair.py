"""A KB chat answer is checked against every passage the model saw, and
rewritten only where two checkers both find a sentence contradicted — the
check and repair the 2026-10-28 error study measured ("must" for the
passage's "should")."""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.services import chat_answer_repair as R
from app.services import chat_service

LABEL_5 = "Subpart D—Post Federal Award Requirements · § 200.308 · part 5"
LABEL_423 = "Subpart E—Cost Principles · § 200.423"
LABEL_HY = "NSF 24-1 PAPPG Chapter VII-B"
PART_5 = ("(10) A no-cost extension of the period of performance. All requests for no-cost extensions should be "
          "submitted at least 10 calendar days before the conclusion of the period of performance.")
PART_423 = "§ 200.423 Alcoholic beverages. The cost of alcoholic beverages is unallowable."
PASSAGES = [
    {"label": LABEL_423, "content": PART_423, "lead_in": None},
    {"label": LABEL_5, "content": PART_5, "lead_in": "(f) Revisions Requiring Prior Approval."},
]
ANSWER = (f"You must submit a no-cost extension request at least 10 calendar days before the period ends. "
          f"[Source: {LABEL_5}]\n"
          f"Alcoholic beverages are unallowable. [Source: {LABEL_423}]")
FIXED = (f"You should submit a no-cost extension request at least 10 calendar days before the period ends. "
         f"[Source: {LABEL_5}]\n"
         f"Alcoholic beverages are unallowable. [Source: {LABEL_423}]")
CONFIG = R.RepairConfig(checker="qwen", second_checker="kimi", repairer="qwen", second_check_seconds=5.0)


def _labels(*flagged, n=2):
    return json.dumps({"sentences": [
        {"n": i, "label": "contradicted" if i in flagged else "ok", "passage": "P2" if i in flagged else None,
         "why": "the passage says 'should be submitted'" if i in flagged else ""}
        for i in range(1, n + 1)
    ]})


def _repair(changed="1", answer=FIXED):
    return f"CHANGED: {changed}\nKEPT: none\nANSWER:\n{answer}"


def _asker(replies, delays=None):
    """An ask that answers each checker by model name and the repair by
    "repair": a reply string, or an exception to raise. Records each call."""
    calls = []

    async def ask(model, instructions, prompt, max_tokens):
        role = "repair" if instructions == R.REPAIR_INSTRUCTIONS else model
        calls.append({"role": role, "model": model, "prompt": prompt})
        await asyncio.sleep((delays or {}).get(role, 0))
        reply = replies[role]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    ask.calls = calls
    return ask


# ------------------------------------------------------------------ setting

def test_the_step_is_off_unless_chat_config_turns_it_on():
    assert R.repair_config(None) is None
    assert R.repair_config({}) is None
    assert R.repair_config({"chat_config": {"microcompact_enabled": True}}) is None
    assert R.repair_config({"chat_config": {"answer_repair_enabled": False}}) is None


def test_on_it_defaults_to_qwen_checking_and_repairing_with_kimi_capped_at_15_s():
    cfg = R.repair_config({"chat_config": {"answer_repair_enabled": True}})
    assert cfg == R.RepairConfig(checker="qwen/qwen3.5-122b", second_checker="moonshotai/kimi-k3",
                                 repairer="qwen/qwen3.5-122b", second_check_seconds=15.0)


def test_an_empty_second_checker_repairs_on_the_first_checkers_flags_alone():
    cfg = R.repair_config({"chat_config": {
        "answer_repair_enabled": True, "answer_repair_checker_model": "a", "answer_repair_second_checker_model": "",
        "answer_repair_model": "b", "answer_repair_second_check_seconds": "x",
    }})
    assert cfg == R.RepairConfig(checker="a", second_checker=None, repairer="b", second_check_seconds=15.0)


def test_only_kb_answers_without_attached_documents_or_other_tools_are_in_scope():
    kb = [{"tool_name": "search_knowledge_base"}, {"tool_name": "list_knowledge_bases"}]
    assert R.in_scope([], attached_documents=False)
    assert R.in_scope(kb, attached_documents=False)
    assert not R.in_scope([], attached_documents=True)
    assert not R.in_scope([*kb, {"tool_name": "fetch_url"}], attached_documents=False)


# ----------------------------------------------------------------- passages

def test_passages_are_the_prefetched_ones_then_the_searched_ones_each_once():
    prefetch = [{"cite_label": "A", "content": "Alpha passage text.", "lead_in": "Lead A"}]
    tools = [
        {"tool_name": "search_knowledge_base", "content": {"results": [
            {"label": "B", "content": "Beta passage text."},
            {"source_name": "a.pdf", "content": "ALPHA   passage text."},   # the same passage again
        ]}},
        {"tool_name": "search_knowledge_base", "content": json.dumps({"results": [{"label": "C", "content": "Gamma."}]})},
        {"tool_name": "search_knowledge_base", "content": "not json"},
        {"tool_name": "list_knowledge_bases", "content": {"results": [{"label": "D", "content": "a KB list"}]}},
    ]
    assert R.seen_passages(prefetch, tools) == [
        {"label": "A", "content": "Alpha passage text.", "lead_in": "Lead A"},
        {"label": "B", "content": "Beta passage text.", "lead_in": None},
        {"label": "C", "content": "Gamma.", "lead_in": None},
    ]


def test_sentences_keep_their_citations_and_name_the_passages_they_cite():
    answer = (f"**Short answer:** no. [Source: {LABEL_423}]\n"
              f"The cost of alcoholic beverages is unallowable. It cannot be charged.\n[Source: {LABEL_423}]\n"
              "Ok.")
    sents = R.split_answer(answer)
    assert sents == [f"**Short answer:** no. [Source: {LABEL_423}]",
                     "The cost of alcoholic beverages is unallowable.",
                     f"It cannot be charged. [Source: {LABEL_423}]"]
    assert [R.cited_ids(s, PASSAGES) for s in sents] == [[1], [], [1]]


def test_the_checker_sees_every_passage_and_each_sentence_with_what_it_cites():
    sents = [(s, R.cited_ids(s, PASSAGES)) for s in R.split_answer(ANSWER)]
    prompt = R.check_prompt("When are extension requests due?", "Earlier?", PASSAGES, sents)
    assert prompt.startswith("QUESTION: When are extension requests due?\nEARLIER QUESTION IN THIS CONVERSATION: Earlier?")
    assert f"[P1] {LABEL_423}\n{PART_423}" in prompt
    assert f"[P2] {LABEL_5}\n[Lead-in, earlier in this section: (f) Revisions Requiring Prior Approval.]\n{PART_5}" in prompt
    assert "S1 (cites P2): You must submit a no-cost extension request" in prompt
    assert "S2 (cites P1): Alcoholic beverages are unallowable." in prompt
    assert "[Source:" not in prompt.split("ANSWER SENTENCES:")[1]


# ------------------------------------------------------------------ parsing

def test_a_checker_reply_is_read_past_think_blocks_and_code_fences():
    reply = "<think>hm</think>\n```json\n" + _labels(1) + "\n```"
    labels = R.parse_check(reply)
    assert labels[0] == {"n": 1, "label": "contradicted", "passage": 2, "why": "the passage says 'should be submitted'"}
    assert [s["n"] for s in R.contradicted(labels, 2)] == [1]


def test_flags_outside_the_answer_or_without_a_number_are_dropped():
    labels = R.parse_check(json.dumps({"sentences": [
        {"n": 7, "label": "contradicted"}, {"n": True, "label": "contradicted"},
        {"n": "1", "label": "contradicted"}, {"n": 2, "label": "Contradicted", "passage": 4}, "junk",
    ]}))
    assert [s["n"] for s in R.contradicted(labels, 2)] == [2]
    assert labels[-1]["passage"] == 4


@pytest.mark.parametrize("reply", ["no json here", "[1, 2]", '{"sentences": "none"}'])
def test_an_unreadable_checker_reply_raises(reply):
    with pytest.raises(ValueError):
        R.parse_check(reply)


def test_a_repair_reply_gives_the_answer_and_the_sentences_it_changed_and_kept():
    answer, changed, kept = R.parse_repair(f"CHANGED: 1, 3\nKEPT: 2\nANSWER:\n{FIXED}\n", PASSAGES)
    assert (answer, changed, kept) == (FIXED, [1, 3], [2])
    assert R.parse_repair(_repair("none"), PASSAGES)[1] == []
    with pytest.raises(ValueError):
        R.parse_repair("CHANGED: 1\nKEPT: none\n", PASSAGES)
    with pytest.raises(ValueError):
        R.parse_repair("CHANGED: 1\nANSWER:\n   \n", PASSAGES)


def test_clean_drops_copied_sentence_prefixes_and_cites_by_label():
    text = ("- **S1** (cites P2): You should submit it 10 days before.\n"
            "S2 (no citation): Ask your sponsored programs office.\n"
            "Alcohol is unallowable [P1]. Both say so [Source: P1; P2], and [P1, P2].")
    assert R.clean(text, PASSAGES) == (
        f"- You should submit it 10 days before. [Source: {LABEL_5}]\n"
        "Ask your sponsored programs office.\n"
        f"Alcohol is unallowable [Source: {LABEL_423}]. Both say so [Source: {LABEL_423}] [Source: {LABEL_5}], "
        f"and [Source: {LABEL_423}] [Source: {LABEL_5}]."
    )


def test_clean_snaps_a_label_retyped_with_other_hyphens_back_to_the_passages_own():
    passages = [{"label": LABEL_HY, "content": "x"}, {"label": LABEL_5, "content": "y"}]
    retyped = "NSF 24‑1 PAPPG Chapter VII‐B"
    assert R.clean(f"It says so. [Source: {retyped}; {LABEL_5}]", passages) == \
        f"It says so. [Source: {LABEL_HY}; {LABEL_5}]"
    assert R.clean("Elsewhere. [Source: Some other guide]", passages) == "Elsewhere. [Source: Some other guide]"


# ---------------------------------------------------------- gate and repair

async def test_both_checkers_flag_and_the_repair_replaces_the_answer():
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1, 2), "repair": _repair()})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, CONFIG, ask, prev_question="Before?")
    assert answer == FIXED
    assert rec["outcome"] == "repaired" and rec["original_answer"] == ANSWER
    assert [c["model"] for c in rec["checks"]] == ["qwen", "kimi"]
    assert [c["flagged"] for c in rec["checks"]] == [[1], [1, 2]]
    assert rec["repair"] == {"model": "qwen", "flagged": [1], "changed": [1], "kept": [], "unchanged": False,
                             "seconds": rec["repair"]["seconds"]}
    # Repaired on the first checker's flags, with its reasons.
    prompt = ask.calls[-1]["prompt"]
    assert "CHECKER FLAGS:\nS1 contradicted by P2: the passage says 'should be submitted'" in prompt
    assert f"ANSWER:\n{ANSWER}\n" in prompt and f"[P2] label: {LABEL_5}" in prompt
    assert "EARLIER QUESTION IN THIS CONVERSATION: Before?" in prompt


async def test_nothing_flagged_by_the_first_checker_ends_the_turn_without_waiting_for_the_second():
    ask = _asker({"qwen": _labels(), "kimi": _labels(1)}, delays={"kimi": 3})
    started = asyncio.get_running_loop().time()
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert asyncio.get_running_loop().time() - started < 1
    assert answer == ANSWER and rec["outcome"] == "no_flags"
    assert rec["checks"][1] == {"model": "kimi", "cancelled": True}
    assert "repair" not in rec and "original_answer" not in rec


async def test_a_second_checker_that_flags_nothing_keeps_the_answer():
    ask = _asker({"qwen": _labels(1), "kimi": _labels()})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "second_check_no_flags"
    assert all(c["role"] != "repair" for c in ask.calls)


async def test_a_second_check_past_its_cap_keeps_the_answer():
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1)}, delays={"kimi": 2})
    config = R.RepairConfig(checker="qwen", second_checker="kimi", repairer="qwen", second_check_seconds=0.1)
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, config, ask)
    assert answer == ANSWER and rec["outcome"] == "second_check_late"
    assert rec["checks"][1]["error"] == "timed_out"
    assert all(c["role"] != "repair" for c in ask.calls)


@pytest.mark.parametrize("first, outcome", [
    (RuntimeError("503 from the endpoint"), "check_failed"),
    ("I could not read the passages.", "check_failed"),
])
async def test_a_failed_or_unreadable_first_check_keeps_the_answer(first, outcome):
    ask = _asker({"qwen": first, "kimi": _labels(1)}, delays={"kimi": 3})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == outcome and rec["checks"][0]["error"]
    assert rec["checks"][1] == {"model": "kimi", "cancelled": True}


async def test_a_failed_second_check_keeps_the_answer():
    ask = _asker({"qwen": _labels(1), "kimi": RuntimeError("down")})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "second_check_failed"


@pytest.mark.parametrize("reply", [_repair("none"), _repair("1", ANSWER), _repair("1", ANSWER + "\n\n")])
async def test_a_repair_that_changes_nothing_keeps_the_stored_answer(reply):
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1), "repair": reply})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "unchanged" and rec["repair"]["unchanged"] is True
    assert "original_answer" not in rec


@pytest.mark.parametrize("reply", [RuntimeError("500"), "CHANGED: 1\nKEPT: none\n"])
async def test_a_failed_or_unreadable_repair_keeps_the_answer(reply):
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1), "repair": reply})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "repair_failed" and rec["repair"]["error"]


async def test_a_repair_past_its_cap_keeps_the_answer(monkeypatch):
    monkeypatch.setattr(R, "REPAIR_SECONDS", 0.1)
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1), "repair": _repair()}, delays={"repair": 2})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == ANSWER and rec["outcome"] == "repair_failed" and rec["repair"]["error"] == "timed_out"


async def test_without_a_second_checker_the_first_checkers_flags_are_repaired():
    config = R.RepairConfig(checker="qwen", second_checker=None, repairer="qwen")
    ask = _asker({"qwen": _labels(1), "repair": _repair()})
    answer, rec = await R.check_and_repair(ANSWER, "q", PASSAGES, config, ask)
    assert answer == FIXED and rec["outcome"] == "repaired"
    assert [c["role"] for c in ask.calls] == ["qwen", "repair"]


async def test_a_repair_is_cleaned_before_it_replaces_the_answer():
    ask = _asker({"qwen": _labels(1), "kimi": _labels(1),
                  "repair": _repair(answer="S1 (cites P2): You should submit it 10 days before.\n"
                                           "Alcoholic beverages are unallowable. [P1]")})
    answer, _ = await R.check_and_repair(ANSWER, "q", PASSAGES, CONFIG, ask)
    assert answer == (f"You should submit it 10 days before. [Source: {LABEL_5}]\n"
                      f"Alcoholic beverages are unallowable. [Source: {LABEL_423}]")


async def test_an_answer_with_no_sentence_to_check_is_not_checked():
    ask = _asker({})
    answer, rec = await R.check_and_repair("Ok.", "q", PASSAGES, CONFIG, ask)
    assert answer == "Ok." and rec["outcome"] == "not_checked" and ask.calls == []


# ------------------------------------------------------------------- models

def test_a_checker_not_in_system_config_runs_on_the_answering_models_endpoint():
    gpt = {"id": "1", "name": "openai/gpt-oss-120b", "endpoint": "https://router/v1", "api_key": "enc", "external": False}
    doc = {"available_models": [gpt]}
    out = R._with_model("qwen/qwen3.5-122b", "openai/gpt-oss-120b", doc)
    assert out["available_models"][1] == {k: v for k, v in gpt.items() if k != "id"} | {"name": "qwen/qwen3.5-122b"}
    assert doc == {"available_models": [gpt]}
    assert R._with_model("openai/gpt-oss-120b", "x", doc) is doc
    assert R._with_model("qwen/qwen3.5-122b", "not-configured", doc) is doc


# --------------------------------------------------------------- chat wiring

def _history(question):
    return [ModelRequest(parts=[UserPromptPart(content=question)]), ModelResponse(parts=[TextPart(content="An answer.")])]


async def test_chat_runs_the_step_only_when_on_and_on_a_kb_answer(monkeypatch):
    seen = []

    async def fake(answer, question, passages, config, ask, *, prev_question=None):
        seen.append({"passages": passages, "prev": prev_question, "config": config})
        return "fixed", {"outcome": "repaired"}

    monkeypatch.setattr(R, "check_and_repair", fake)
    monkeypatch.setattr(R, "model_ask", lambda model, doc: None)
    on = {"chat_config": {"answer_repair_enabled": True}}
    src = [{"label": LABEL_5, "cite_label": LABEL_5, "content": PART_5, "lead_in": None, "ref": 1}]

    async def run(doc, sources=src, tools=(), docs=False, answer="a"):
        return await chat_service._repair_answer(answer, "q", sources, list(tools), docs, _history("Earlier?"), "m", doc)

    assert await run({}) == ("a", None)
    assert await run(on, docs=True) == ("a", None)
    assert await run(on, tools=[{"tool_name": "web_search", "content": {}}]) == ("a", None)
    assert await run(on, sources=[]) == ("a", None)
    assert await run(on, answer="  ") == ("  ", None)
    assert seen == []
    assert await run(on) == ("fixed", {"outcome": "repaired"})
    assert seen[0]["passages"] == [{"label": LABEL_5, "content": PART_5, "lead_in": None}]
    assert seen[0]["prev"] == "Earlier?" and seen[0]["config"].second_checker == "moonshotai/kimi-k3"


async def test_chat_keeps_the_answer_when_the_step_raises(monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("bug")

    monkeypatch.setattr(R, "check_and_repair", boom)
    monkeypatch.setattr(R, "model_ask", lambda model, doc: None)
    src = [{"label": LABEL_5, "content": PART_5}]
    out = await chat_service._repair_answer("a", "q", src, [], False, [], "m", {"chat_config": {"answer_repair_enabled": True}})
    assert out == ("a", None)
