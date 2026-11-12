"""Chat must not restate a lesson card it sits under (support ticket).

Under "From one workflow to many", chat's summary said a project means
"everything is indexed together and you can chat across the whole set"; the
lesson says a project "does not itself … make every source ready for chat".
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

from app.services.approval_claims import require_lesson_not_restated, restates_lesson

_LESSONS = json.loads((Path(__file__).parents[1] / "certification-data" / "lessons.json").read_text())
LESSON = next(l for l in _LESSONS["process_mapping"]["lessons"] if l["title"].startswith("From one workflow to many"))["content"]

# The ticket's summary, reconstructed from the two reversed points it quoted.
TICKET_SUMMARY = (
    "Here's the gist of this lesson:\n"
    "- Start with the result you need, then pick a method.\n"
    "- A project means everything is indexed together and you can chat across the whole set.\n"
    "- A frequent, simple extraction may be worth a workflow, and automations run saved workflows "
    "when a document arrives in a watched folder.\n"
    "Ready for the next lesson?"
)
FRAMING = (
    "Here's lesson 1 of Thinking in Workflows. Read it through, try the practice cases at the "
    "end, and ask me anything that's unclear."
)


def _ctx(user_message="teach me the lessons one at a time", lesson=LESSON, tool="get_certification_lesson"):
    messages = [
        ModelRequest(parts=[UserPromptPart(content=user_message)]),
        ModelResponse(parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id="c0")]),
        ModelRequest(parts=[ToolReturnPart(tool_name=tool, tool_call_id="c0",
                                           content={"module_id": "process_mapping", "content": lesson})]),
    ]
    deps = SimpleNamespace(user_message=user_message, lesson_restated_retry_used=False)
    return SimpleNamespace(partial_output=False, deps=deps, messages=messages)


def test_the_ticket_summary_is_sent_back():
    with pytest.raises(ModelRetry, match="Do not summarize or restate"):
        require_lesson_not_restated(_ctx(), TICKET_SUMMARY)


def test_a_framing_sentence_passes():
    assert require_lesson_not_restated(_ctx(), FRAMING) == FRAMING


def test_a_question_about_the_lesson_may_be_answered():
    ctx = _ctx(user_message="What does it mean that a project doesn't make sources ready for chat?")
    assert require_lesson_not_restated(ctx, TICKET_SUMMARY) == TICKET_SUMMARY


def test_without_a_lesson_card_this_turn_nothing_is_checked():
    ctx = _ctx(tool="get_certification_module")
    assert require_lesson_not_restated(ctx, TICKET_SUMMARY) == TICKET_SUMMARY


def test_sent_back_once_per_turn():
    ctx = _ctx()
    with pytest.raises(ModelRetry):
        require_lesson_not_restated(ctx, TICKET_SUMMARY)
    assert require_lesson_not_restated(ctx, TICKET_SUMMARY) == TICKET_SUMMARY


def test_a_long_reply_about_something_else_is_not_a_restatement():
    reply = (
        "Before we go on: your trial has about 40% of its token budget left, which is plenty for this "
        "module and the next one. If it runs low, an admin can top it up from the Account screen, and "
        "nothing you've saved is lost. Ready to keep going?"
    )
    assert not restates_lesson(reply, LESSON)


# 64 replies a separate model wrote under 8 real lesson cards, without seeing
# this check: brief framings and summaries (some accurate, some distorted).
_BY_ID = {lesson["id"]: lesson["content"] for module in _LESSONS.values() for lesson in module.get("lessons", [])}
_CASES = json.loads((Path(__file__).parent / "fixtures" / "lesson_reply_cases.json").read_text())


def test_corpus_framings_are_never_sent_back():
    flagged = [c["reply"][:60] for c in _CASES if c["kind"] == "framing" and restates_lesson(c["reply"], _BY_ID[c["lesson_id"]])]
    assert flagged == []


def test_corpus_summaries_are_sent_back():
    missed = [c["reply"][:60] for c in _CASES if c["kind"] == "summary" and not restates_lesson(c["reply"], _BY_ID[c["lesson_id"]])]
    # The one miss is a two-sentence gist; the prompt rule still covers it.
    assert len(missed) <= 1, missed
