"""The completeness extension of the KB answer repair: the two checkers also
list what the passages state about the question that the answer leaves out,
and the repair adds the points both name from the same passage. Off, the
study's prompts and flow are untouched."""

import asyncio
import json

from app.services import chat_answer_repair as R

LABEL_5 = "Subpart D—Post Federal Award Requirements · § 200.308 · part 5"
LABEL_423 = "Subpart E—Cost Principles · § 200.423"
PART_5 = ("(10) A no-cost extension of the period of performance. All requests for no-cost extensions should be "
          "submitted at least 10 calendar days before the conclusion of the period of performance.")
PART_423 = "§ 200.423 Alcoholic beverages. The cost of alcoholic beverages is unallowable."
PASSAGES = [
    {"label": LABEL_423, "content": PART_423, "lead_in": None},
    {"label": LABEL_5, "content": PART_5, "lead_in": "(f) Revisions Requiring Prior Approval."},
]
ANSWER = (f"You should submit a no-cost extension request before the period ends. [Source: {LABEL_5}]\n"
          f"Alcoholic beverages are unallowable. [Source: {LABEL_423}]")
ADDED = (f"You should submit a no-cost extension request before the period ends. [Source: {LABEL_5}]\n"
         f"Requests should be submitted at least 10 calendar days before the conclusion of the period of "
         f"performance. [Source: {LABEL_5}]\n"
         f"Alcoholic beverages are unallowable. [Source: {LABEL_423}]")
TEN_DAYS = "at least 10 calendar days before the conclusion of the period of performance"
OFF = R.RepairConfig(checker="qwen", second_checker="kimi", repairer="qwen", second_check_seconds=5.0)
ON = R.RepairConfig(checker="qwen", second_checker="kimi", repairer="qwen", second_check_seconds=5.0,
                    completeness=True)
ALONE = R.RepairConfig(checker="qwen", second_checker=None, repairer="qwen", completeness=True)


def _reply(*flagged, missing=(), n=2):
    return json.dumps({
        "sentences": [{"n": i, "label": "contradicted" if i in flagged else "ok",
                       "passage": "P2" if i in flagged else None,
                       "why": "the passage says 'at least 10 calendar days'" if i in flagged else ""}
                      for i in range(1, n + 1)],
        "missing": [{"passage": p, "what": w} for p, w in missing],
    })


def _repair(changed="none", added="1", answer=ADDED):
    return f"CHANGED: {changed}\nKEPT: none\nADDED: {added}\nANSWER:\n{answer}"


def _asker(replies, delays=None):
    """An ask that answers each checker by model name and the repair by
    "repair"; records each call with the instructions it was given."""
    calls = []

    async def ask(model, instructions, prompt, max_tokens):
        role = "repair" if instructions in (R.REPAIR_INSTRUCTIONS, R.REPAIR_COMPLETENESS_INSTRUCTIONS) else model
        calls.append({"role": role, "model": model, "instructions": instructions, "prompt": prompt})
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

def test_completeness_is_off_unless_chat_config_turns_it_on():
    assert R.repair_config({"chat_config": {"answer_repair_enabled": True}}).completeness is False
    on = {"chat_config": {"answer_repair_enabled": True, "answer_repair_completeness_enabled": True}}
    assert R.repair_config(on).completeness is True
    assert R.repair_config({"chat_config": {"answer_repair_completeness_enabled": True}}) is None


def test_the_studys_prompts_are_the_same_without_the_extension():
    assert "missing" not in R.CHECK_INSTRUCTIONS and R.CHECK_INSTRUCTIONS.startswith("You check an assistant's answer")
    assert R.CHECK_INSTRUCTIONS.endswith('quote the conflicting passage words>"}]}')
    assert R.COMPLETENESS_INSTRUCTIONS.startswith(R._CHECK_TASK)
    assert "Then list what the passages state about the question that the answer leaves out" in R._MISSING_TASK
    assert '"missing": [{"passage": <P number>' in R.COMPLETENESS_INSTRUCTIONS
    assert "ADDED:" not in R.REPAIR_INSTRUCTIONS and R.REPAIR_INSTRUCTIONS.endswith("<the full corrected answer>")
    assert R.REPAIR_COMPLETENESS_INSTRUCTIONS.startswith(R._REPAIR_TASK)
    assert "ADDED: <numbers of the missing points you added" in R.REPAIR_COMPLETENESS_INSTRUCTIONS


# ------------------------------------------------------------------ parsing

def test_a_checker_reply_lists_the_missing_points_that_name_a_passage():
    text = json.dumps({"sentences": [{"n": 1, "label": "ok"}],
                       "missing": [{"passage": "P2", "what": " ten days "}, {"passage": None, "what": "x"},
                                   {"passage": 1, "what": ""}, "junk", {"passage": "3", "what": "y"}]})
    labels, missing = R.parse_reply(text)
    assert [s["label"] for s in labels] == ["ok"]
    assert missing == [{"passage": 2, "what": "ten days"}, {"passage": 3, "what": "y"}]
    assert R.parse_check(text) == labels
    assert R.parse_reply(json.dumps({"sentences": []}))[1] == []
    assert R.missing_points(missing, 2) == [{"passage": 2, "what": "ten days"}]


def test_a_missing_point_counts_when_both_checkers_name_its_passage_at_most_three():
    first = [{"passage": 2, "what": "a"}, {"passage": 1, "what": "b"}, {"passage": 2, "what": "c"},
             {"passage": 1, "what": "d"}, {"passage": 2, "what": "e"}]
    second = [{"passage": 2, "what": "other words"}]
    assert R.confirmed_missing(first, second) == [first[0], first[2], first[4]][:3]
    assert R.confirmed_missing(first, []) == []
    assert R.confirmed_missing(first, None) == first[:3]


def test_a_repair_reply_says_which_missing_points_it_added():
    assert R.parse_added("CHANGED: none\nKEPT: none\nADDED: 1, 3\nANSWER:\nx") == [1, 3]
    assert R.parse_added("CHANGED: 1\nKEPT: none\nANSWER:\nx") == []
    assert R.parse_repair(_repair(), PASSAGES)[1:] == ([], [])


def test_the_repair_prompt_lists_the_missing_points_after_the_flags():
    sents = [(s, R.cited_ids(s, PASSAGES)) for s in R.split_answer(ANSWER)]
    missing = [{"passage": 2, "what": TEN_DAYS}]
    prompt = R.repair_prompt("When?", None, PASSAGES, ANSWER, sents, [], missing)
    assert prompt.endswith(f"CHECKER FLAGS:\nnone\n\nMISSING FROM THE ANSWER:\nM1 (stated by P2): {TEN_DAYS}")
    flags = [{"n": 1, "passage": 2, "why": "says should"}]
    both = R.repair_prompt("When?", None, PASSAGES, ANSWER, sents, flags, missing)
    assert "CHECKER FLAGS:\nS1 contradicted by P2: says should\n\nMISSING FROM THE ANSWER:\nM1" in both
    # Without the extension the study's prompt ends with the flags, as before.
    assert R.repair_prompt("When?", None, PASSAGES, ANSWER, sents, flags).endswith("S1 contradicted by P2: says should")


# --------------------------------------------------------------------- flow

async def test_both_checkers_name_a_missing_point_from_the_same_passage_and_the_repair_adds_it():
    ask = _asker({"qwen": _reply(missing=[("P2", TEN_DAYS)]),
                  "kimi": _reply(missing=[(2, "the 10 calendar days")]),
                  "repair": _repair()})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
    assert answer == ADDED
    assert rec["completeness"] is True and rec["outcome"] == "repaired" and rec["original_answer"] == ANSWER
    assert [c["missing"] for c in rec["checks"]] == [[{"passage": 2, "what": TEN_DAYS}],
                                                     [{"passage": 2, "what": "the 10 calendar days"}]]
    assert rec["repair"] == {"model": "qwen", "flagged": [], "missing": [{"passage": 2, "what": TEN_DAYS}],
                             "changed": [], "kept": [], "unchanged": False, "added": [1],
                             "seconds": rec["repair"]["seconds"]}
    # Both checkers were asked with the extended instructions, the repairer too, given the first checker's wording.
    assert [c["instructions"] for c in ask.calls[:2]] == [R.COMPLETENESS_INSTRUCTIONS] * 2
    assert ask.calls[-1]["instructions"] == R.REPAIR_COMPLETENESS_INSTRUCTIONS
    assert f"CHECKER FLAGS:\nnone\n\nMISSING FROM THE ANSWER:\nM1 (stated by P2): {TEN_DAYS}" in ask.calls[-1]["prompt"]


async def test_a_missing_point_only_one_checker_finds_or_from_another_passage_keeps_the_answer():
    for second in (_reply(), _reply(missing=[(1, "alcohol")])):
        ask = _asker({"qwen": _reply(missing=[("P2", TEN_DAYS)]), "kimi": second})
        answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
        assert answer == ANSWER and rec["outcome"] == "second_check_no_flags"
        assert all(c["role"] != "repair" for c in ask.calls) and "repair" not in rec


async def test_a_contradiction_and_a_missing_point_are_repaired_together():
    fixed = ADDED.replace("You should submit", "You must submit")
    ask = _asker({"qwen": _reply(1, missing=[("P2", TEN_DAYS)]), "kimi": _reply(1, missing=[(2, "ten days")]),
                  "repair": _repair(changed="1", added="1", answer=fixed)})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
    assert answer == fixed and rec["outcome"] == "repaired"
    assert rec["repair"]["flagged"] == [1] and rec["repair"]["changed"] == [1] and rec["repair"]["added"] == [1]
    assert "S1 contradicted by P2: the passage says 'at least 10 calendar days'\n\nMISSING FROM THE ANSWER:\nM1" \
        in ask.calls[-1]["prompt"]


async def test_a_contradiction_the_second_checker_does_not_confirm_is_not_rewritten_but_the_missing_point_is_added():
    ask = _asker({"qwen": _reply(1, missing=[("P2", TEN_DAYS)]), "kimi": _reply(missing=[(2, "ten days")]),
                  "repair": _repair()})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
    assert answer == ADDED and rec["outcome"] == "repaired"
    assert rec["repair"]["flagged"] == [] and rec["repair"]["missing"] == [{"passage": 2, "what": TEN_DAYS}]
    assert "CHECKER FLAGS:\nnone" in ask.calls[-1]["prompt"]


async def test_a_repair_that_claims_no_addition_keeps_the_stored_answer():
    ask = _asker({"qwen": _reply(missing=[("P2", TEN_DAYS)]), "kimi": _reply(missing=[(2, "ten days")]),
                  "repair": _repair(added="none")})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
    assert answer == ANSWER and rec["outcome"] == "unchanged" and rec["repair"]["added"] == []


async def test_nothing_contradicted_and_nothing_missing_ends_the_turn_without_waiting_for_the_second_checker():
    ask = _asker({"qwen": _reply(), "kimi": _reply(missing=[(2, "ten days")])}, delays={"kimi": 3})
    started = asyncio.get_running_loop().time()
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ON, ask)
    assert asyncio.get_running_loop().time() - started < 1
    assert answer == ANSWER and rec["outcome"] == "no_flags"
    assert rec["checks"][0]["missing"] == [] and rec["checks"][1] == {"model": "kimi", "cancelled": True}


async def test_without_a_second_checker_the_first_checkers_missing_points_are_added():
    ask = _asker({"qwen": _reply(missing=[("P2", TEN_DAYS), ("P9", "no such passage")]), "repair": _repair()})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, ALONE, ask)
    assert answer == ADDED and rec["outcome"] == "repaired"
    assert rec["checks"][0]["missing"] == [{"passage": 2, "what": TEN_DAYS}]
    assert rec["repair"]["missing"] == [{"passage": 2, "what": TEN_DAYS}]


async def test_with_the_extension_off_the_checkers_get_the_studys_prompt_and_missing_points_are_ignored():
    ask = _asker({"qwen": _reply(missing=[("P2", TEN_DAYS)]), "kimi": _reply(missing=[(2, "ten days")])})
    answer, rec = await R.check_and_repair(ANSWER, "When?", PASSAGES, OFF, ask)
    assert answer == ANSWER and rec["outcome"] == "no_flags" and "completeness" not in rec
    assert "missing" not in rec["checks"][0]
    assert ask.calls[0]["instructions"] == R.CHECK_INSTRUCTIONS
