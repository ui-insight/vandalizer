"""Each cited claim of a chat answer is checked against the passage it
cites, and a claim the passage does not state is marked — the check the
word-overlap test could not make ("must" for "should"; a prior-approval
list item read as allowed)."""

import asyncio
import json
import re

import pytest

from app.services import chat_claim_check as C
from app.services import chat_service
from app.services.kb_answer_grounding import expand_snippet_refs

LABEL_4 = "Subpart D—Post Federal Award Requirements · § 200.308 · part 4"
LABEL_5 = "Subpart D—Post Federal Award Requirements · § 200.308 · part 5"
LABEL_423 = "Subpart E—Cost Principles · § 200.423"
LEAD_F = ("(f) Revisions Requiring Prior Approval. A recipient or subrecipient must request prior written approval "
          "from the Federal agency or pass-through entity for the following program and budget-related reasons:")
PART_4 = ("(4) The inclusion, unless waived by the Federal agency, of costs that require prior approval.\n"
          "(5) The transfer of funds budgeted for participant support costs to other budget categories.")
PART_5 = ("(10) A no-cost extension of the period of performance. All requests for no-cost extensions should be "
          "submitted at least 10 calendar days before the conclusion of the period of performance. The Federal "
          "agency may approve multiple no-cost extensions under a Federal award if not prohibited by Federal "
          "statute or regulation.")


def _source(label, content, lead=None, title=None):
    return {"label": label, "cite_label": label, "content": content, "lead_in": lead,
            "document_title": title or label.split(" · ")[0]}


SOURCES = [
    _source(LABEL_4, PART_4, LEAD_F),
    _source(LABEL_5, PART_5),
    _source(LABEL_423, "§ 200.423 Alcoholic beverages.\n\nThe cost of alcoholic beverages is unallowable."),
]


def _asker(replies):
    """An ask that answers each call with the next reply, recording prompts.
    A reply is a dict of claim text → item, matched by the claim's words."""
    prompts = []

    async def ask(instructions, prompt):
        prompts.append(prompt)
        claims = [json.loads(line) for line in prompt.split("\n\n") if line.startswith('{"id"')]
        ids = dict(re.findall(r'<passage id="(P\d+)" source="([^"]*)"', prompt))
        by_label = {v: k for k, v in ids.items()}
        items = []
        for c in claims:
            reply = next((r for key, r in replies.items() if key in c["claim"]), {"supported": False})
            item = {"id": c["id"], **reply}
            if "label" in item:
                item["passage"] = by_label[item.pop("label")]
            if "quotes" in item:
                item["quotes"] = [{"passage": by_label[q["label"]], "quote": q["quote"]} for q in item["quotes"]]
            items.append(item)
        return json.dumps({"items": items})

    ask.prompts = prompts
    return ask


def _check(answer, replies, question="q"):
    return asyncio.run(C.check_claims(answer, SOURCES, question, _asker(replies)))


def _statuses(result):
    return [(c["claim"], c["status"], c.get("reason")) for c in result["claims"]]


class TestClaims:
    def test_each_cited_statement_is_a_claim_with_its_passages(self):
        answer = (f"- Moving them **requires prior written approval** [Source: {LABEL_4}].\n"
                  f"- Beer is unallowable. [Source: {LABEL_423}]\n"
                  "- Always check your award terms.")
        claims = C.cited_claims(answer, SOURCES)
        assert [(c.statement.text, c.sources) for c in claims] == [
            ("Moving them requires prior written approval", [0]),
            ("Beer is unallowable.", [2]),
        ]
        assert claims[0].citations == [f"Source: {LABEL_4}"]

    def test_a_bracket_naming_no_retrieved_passage_is_not_a_claim(self):
        assert C.cited_claims("Beer is unallowable [Source: Some other guide · p. 3].", SOURCES) == []

    def test_one_bracket_citing_two_passages(self):
        claims = C.cited_claims(f"Both say so [Source: {LABEL_4}; {LABEL_5}].", SOURCES)
        assert claims[0].sources == [0, 1]


class TestVerify:
    def test_must_from_should_is_refused_even_with_a_figure(self):
        answer = f"All requests must be submitted at least 10 calendar days before the end [Source: {LABEL_5}]."
        quote = ("All requests for no-cost extensions should be submitted at least 10 calendar days before the "
                 "conclusion of the period of performance.")
        result = _check(answer, {"must be submitted": {"supported": True, "label": LABEL_5, "quote": quote}})
        assert _statuses(result)[0][1:] == ("unverified", "obligation_differs")

    def test_permission_read_into_a_bare_list_item_is_refused(self):
        bare = [{**SOURCES[0], "lead_in": None}, *SOURCES[1:]]
        answer = f"The Uniform Guidance permits transferring participant support funds to travel [Source: {LABEL_4}]."
        quote = "(5) The transfer of funds budgeted for participant support costs to other budget categories."
        replies = {"permits": {"supported": True, "label": LABEL_4, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, bare, "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("unverified", "modality_differs")

    def test_an_item_read_with_its_lead_in_is_verified(self):
        answer = f"Transferring participant support funds requires prior written approval [Source: {LABEL_4}]."
        quote = "(5) The transfer of funds budgeted for participant support costs to other budget categories."
        result = _check(answer, {"requires": {"supported": True, "label": LABEL_4, "quote": quote}})
        assert _statuses(result)[0][1:] == ("verified", "ok")
        assert result["claims"][0]["quote"] == quote

    def test_a_rule_applied_to_the_question_and_a_named_regulation_pass(self):
        answer = (f"No. Under the Uniform Guidance (2 CFR 200), the cost of alcoholic beverages is unallowable — "
                  f"that includes beer at a lab party. [Source: {LABEL_423}]")
        quote = "The cost of alcoholic beverages is unallowable."
        result = _check(answer, {"alcoholic": {"supported": True, "label": LABEL_423, "quote": quote}})
        assert _statuses(result)[0][1] == "verified"

    def test_a_figure_not_in_the_passage_is_refused_unless_the_user_gave_it(self):
        answer = f"Requests are due 30 calendar days before the end [Source: {LABEL_5}]."
        quote = "All requests for no-cost extensions should be submitted at least 10 calendar days"
        replies = {"due": {"supported": True, "label": LABEL_5, "quote": quote}}
        assert _statuses(_check(answer, replies))[0][2] == "value_not_in_quote"

    def test_a_quote_ending_its_sentence_is_not_read_into_the_next(self):
        passage = _source(LABEL_5, "This paragraph does not preclude the Federal agency from approving further "
                                   "no-cost extensions. One-time extensions require prior approval when:")
        answer = f"The agency may still approve further no-cost extensions [Source: {LABEL_5}]."
        quote = "This paragraph does not preclude the Federal agency from approving further no-cost extensions."
        replies = {"still": {"supported": True, "label": LABEL_5, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, [passage], "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("verified", "ok")

    def test_a_claim_resting_on_two_passages_has_an_excerpt_from_each(self):
        answer = (f"The list of prior approvals includes no-cost extensions [Source: {LABEL_5}] and moving "
                  f"participant support funds to other categories [Source: {LABEL_4}].")
        replies = {"no-cost": {"supported": True, "quotes": [
            {"label": LABEL_5, "quote": "(10) A no-cost extension of the period of performance."},
            {"label": LABEL_4, "quote": "(5) The transfer of funds budgeted for participant support costs"},
        ]}}
        result = _check(answer, replies)
        assert _statuses(result)[0][1:] == ("verified", "ok")
        assert result["claims"][0]["cites"] == [1, 0]

    def test_a_one_word_piece_of_an_excerpt_is_dropped(self):
        quote = "may approve multiple no-cost extensions … (10) … if not prohibited by Federal statute or regulation"
        answer = f"The agency may approve multiple no-cost extensions unless a statute prohibits them [Source: {LABEL_5}]."
        replies = {"multiple": {"supported": True, "label": LABEL_5, "quote": quote}}
        assert _statuses(_check(answer, replies))[0][1] == "verified"

    def test_allowable_only_if_is_unallowable_unless(self):
        entertainment = _source(LABEL_423, "(a) Entertainment costs. Costs of entertainment are unallowable unless "
                                           "they have a specific and direct programmatic purpose and are included "
                                           "in a Federal award.")
        answer = (f"They become allowable only if they have a specific and direct programmatic purpose and are "
                  f"included in the award — otherwise they must not be charged [Source: {LABEL_423}].")
        quote = ("Costs of entertainment are unallowable unless they have a specific and direct programmatic purpose "
                 "and are included in a Federal award.")
        replies = {"allowable only": {"supported": True, "label": LABEL_423, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, [entertainment], "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("verified", "ok")

    def test_a_heading_and_its_rule_are_one_limit_not_two_merged(self):
        threshold = _source(LABEL_5, "(iv) Recipient increase to the micro-purchase threshold up to $50,000. The "
                                     "recipient may self-certify a threshold up to $50,000 on an annual basis.")
        answer = f"For increases up to $50,000, you can self-certify annually [Source: {LABEL_5}]."
        quote = ("Recipient increase to the micro-purchase threshold up to $50,000. The recipient may self-certify "
                 "a threshold up to $50,000 on an annual basis.")
        replies = {"self-certify": {"supported": True, "label": LABEL_5, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, [threshold], "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("verified", "ok")

    def test_two_limits_on_separate_lines_merged_into_one_are_refused(self):
        caps = _source(LABEL_5, "(1) Up to $10,000 should be budgeted for REU student support.\n"
                                "(2) Up to $10,000 should be budgeted for local staff of the Summer Institute.")
        answer = f"Up to $10,000 should be budgeted for REU students and the Summer Institute [Source: {LABEL_5}]."
        quote = ("Up to $10,000 should be budgeted for REU student support. … Up to $10,000 should be budgeted "
                 "for local staff of the Summer Institute.")
        replies = {"REU": {"supported": True, "label": LABEL_5, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, [caps], "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("unverified", "values_merged")

    def test_a_number_word_names_no_figure(self):
        answer = f"The agency may approve multiple no-cost extensions for a single award [Source: {LABEL_5}]."
        quote = "The Federal agency may approve multiple no-cost extensions under a Federal award"
        replies = {"single": {"supported": True, "label": LABEL_5, "quote": quote}}
        assert _statuses(_check(answer, replies))[0][1] == "verified"

    def test_a_limit_is_compared_only_where_its_figure_is(self):
        extension = _source(LABEL_5, "(2) One-time extensions. Initiate a one-time extension of the period of "
                                     "performance by up to 12 months. However, the recipient must notify the agency "
                                     "at least 10 calendar days before the conclusion.")
        answer = f"A one-time extension of up to 12 months needs a notice to the agency [Source: {LABEL_5}]."
        quote = ("Initiate a one-time extension of the period of performance by up to 12 months … the recipient must "
                 "notify the agency at least 10 calendar days before the conclusion.")
        replies = {"one-time": {"supported": True, "label": LABEL_5, "quote": quote}}
        result = asyncio.run(C.check_claims(answer, [extension], "q", _asker(replies)))
        assert _statuses(result)[0][1:] == ("verified", "ok")
        turned = f"A one-time extension of at least 12 months is allowed [Source: {LABEL_5}]."
        result = asyncio.run(C.check_claims(turned, [extension], "q", _asker(
            {"one-time": {"supported": True, "label": LABEL_5, "quote": quote}})))
        assert _statuses(result)[0][2] == "limit_differs"

    def test_a_quote_not_in_the_passage_is_refused(self):
        answer = f"Multiple extensions may be approved [Source: {LABEL_5}]."
        replies = {"Multiple": {"supported": True, "label": LABEL_5, "quote": "Extensions are unlimited."}}
        assert _statuses(_check(answer, replies))[0][2] == "quote_not_in_passage"

    def test_the_checkers_no_is_kept_with_its_reason(self):
        answer = f"Moving the funds needs no approval [Source: {LABEL_4}]."
        result = _check(answer, {"needs no": {"supported": False, "why": "the list requires approval"}})
        claim = result["claims"][0]
        assert (claim["status"], claim["reason"], claim["why"]) == ("unverified", "not_stated", "the list requires approval")
        assert claim["votes"] == "0/3"

    def test_the_passage_named_must_be_one_the_claim_cites(self):
        answer = f"Beer is unallowable [Source: {LABEL_423}]."
        replies = {"Beer": {"supported": True, "passage": "P9", "quote": "The cost of alcoholic beverages is unallowable."}}
        assert _statuses(_check(answer, replies))[0][1] == "unverified"


class TestVotes:
    def test_a_majority_of_readings_decides(self):
        calls = {"n": 0}
        quote = "The cost of alcoholic beverages is unallowable."

        async def ask(instructions, prompt):
            calls["n"] += 1
            ok = calls["n"] != 2      # one reading of three says no
            item = {"id": 1, "supported": ok, "passage": "P1", "quote": quote} if ok else {"id": 1, "supported": False}
            return json.dumps({"items": [item]})

        result = asyncio.run(C.check_claims(f"Beer is unallowable [Source: {LABEL_423}].", SOURCES, "q", ask))
        assert calls["n"] == C.VOTES and result["claims"][0]["status"] == "verified"

    def test_a_failed_call_leaves_claims_unchecked_never_unverified(self):
        async def ask(instructions, prompt):
            raise RuntimeError("model down")

        result = asyncio.run(C.check_claims(f"Beer is unallowable [Source: {LABEL_423}].", SOURCES, "q", ask))
        assert result["claims"][0]["status"] == "unchecked"
        assert result["summary"] == {"verified": 0, "unverified": 0, "unchecked": 1}

    def test_running_out_of_time_leaves_claims_unchecked(self):
        async def ask(instructions, prompt):
            await asyncio.sleep(5)
            return "{}"

        result = asyncio.run(C.check_claims(f"Beer is unallowable [Source: {LABEL_423}].", SOURCES, "q", ask,
                                            timeout=0.05))
        assert result["claims"][0]["reason"] == "timed_out"

    def test_an_answer_citing_nothing_is_not_checked(self):
        assert asyncio.run(C.check_claims("No passage covers this.", SOURCES, "q", _asker({}))) is None

    def test_the_checker_reads_the_question_the_lead_in_and_where_a_claim_sits(self):
        ask = _asker({})
        answer = f"**Prior approval is required when:**\n- The extension changes the scope [Source: {LABEL_4}]"
        asyncio.run(C.check_claims(answer, SOURCES, "Can we move funds?", ask))
        prompt = ask.prompts[0]
        assert prompt.startswith("USER QUESTION\nCan we move funds?")
        assert f"Lead-in (earlier in the same section): {LEAD_F}" in prompt
        assert '"under": "Prior approval is required when"' in prompt


class TestModality:
    @pytest.mark.parametrize("text, expected", [
        ("Transfers require prior written approval.", {"required"}),
        ("Prior approval is not required if authorized.", {"permitted"}),
        ("The cost of alcoholic beverages is unallowable.", {"forbidden"}),
        ("Requests should be submitted early.", {"advised"}),
        ("You cannot move them without prior approval.", {"required"}),
        ("(5) The transfer of funds budgeted for participant support costs.", set()),
        ("An extension that does not require additional funds.", {"permitted"}),
        ("This paragraph does not preclude the agency from approving further extensions.", {"permitted"}),
    ])
    def test_what_a_text_says_of_an_action(self, text, expected):
        assert C.modality(text) == expected


@pytest.mark.asyncio
async def test_chat_checks_only_passages_and_can_be_turned_off(monkeypatch):
    seen = {}

    async def fake_check(answer, sources, question, ask, **kw):
        seen["sources"] = sources
        return {"claims": []}

    monkeypatch.setenv(chat_service.CLAIM_CHECK_ENV, "on")
    monkeypatch.setattr(C, "check_claims", fake_check)
    monkeypatch.setattr(C, "model_ask", lambda model, cfg: None)
    derived = {"document_title": "budget.pdf", "page": 3, "content_preview": "…"}
    out = await chat_service._check_cited_claims("a", "q", [derived, SOURCES[2]], "m", {})
    assert out == {"claims": []} and seen["sources"] == [{}, SOURCES[2]]

    monkeypatch.setenv(chat_service.CLAIM_CHECK_ENV, "off")
    assert await chat_service._check_cited_claims("a", "q", [SOURCES[2]], "m", {}) is None


@pytest.mark.asyncio
async def test_chat_skips_the_check_when_no_passage_was_retrieved(monkeypatch):
    monkeypatch.setenv(chat_service.CLAIM_CHECK_ENV, "on")
    derived = {"document_title": "budget.pdf", "page": 3}
    assert await chat_service._check_cited_claims("a", "q", [derived], "m", {}) is None


@pytest.mark.parametrize("written", ["[**S2**]", "(S2)", "(**S2**)"])
def test_a_snippet_number_bolded_or_in_parentheses_is_still_expanded(written):
    sources = [{"ref": 2, "cite_label": LABEL_5}]
    assert expand_snippet_refs(f"Due 10 days before {written}.", sources) == f"Due 10 days before [Source: {LABEL_5}]."


def test_parentheses_that_hold_no_snippet_number_stay():
    sources = [{"ref": 2, "cite_label": LABEL_5}]
    assert expand_snippet_refs("Form SF-424 (S9) and (see 2).", sources) == "Form SF-424 (S9) and (see 2)."
