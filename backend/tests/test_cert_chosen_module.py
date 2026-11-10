"""Chat opens the module the learner chose, including a completed one.

Support ticket: a learner who had completed Modules 1-4 typed "I want to start
certification from beginning", was offered two options, and replied "from 1
AI Literacy". Chat repeated the options, then opened Extraction Engine
(Module 5), said it could not skip backward and pasted that lesson as plain
text; AI Literacy, Lesson 1 opened only on the fifth message.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

from app.services import llm_service
from app.services.approval_claims import chosen_module, require_chosen_module

MODULES = [
    ("ai_literacy", "AI Literacy"), ("foundations", "Foundations"), ("process_mapping", "Thinking in Workflows"),
    ("workflow_design", "Workflow Design"), ("extraction_engine", "Extraction Engine"),
]
PROGRESS = {"modules": [{"module_id": m, "title": t, "completed": i < 4} for i, (m, t) in enumerate(MODULES)],
            "next_module_id": "extraction_engine"}


def _ctx(user_message, *, opened=(), earlier_course_turn=True):
    history = []
    if earlier_course_turn:
        history = [
            ModelRequest(parts=[UserPromptPart(content="I want to start certification from beginning.")]),
            ModelResponse(parts=[ToolCallPart(tool_name="get_certification_progress", args={}, tool_call_id="p")]),
            ModelRequest(parts=[ToolReturnPart(tool_name="get_certification_progress", tool_call_id="p", content=PROGRESS)]),
        ]
    turn = [ModelRequest(parts=[UserPromptPart(content=user_message)])]
    for i, module_id in enumerate(opened):
        turn += [
            ModelResponse(parts=[ToolCallPart(tool_name="get_certification_lesson",
                                              args={"module_id": module_id, "lesson_number": 1}, tool_call_id=f"l{i}")]),
            ModelRequest(parts=[ToolReturnPart(tool_name="get_certification_lesson", tool_call_id=f"l{i}",
                                               content={"module_id": module_id, "lesson_number": 1})]),
        ]
    deps = SimpleNamespace(user_message=user_message, chosen_module_retry_used=False)
    return SimpleNamespace(partial_output=False, deps=deps, messages=history + turn)


class TestChosenModule:
    @pytest.mark.parametrize("message,module_id,lesson", [
        ("from 1 AI Literacy", "ai_literacy", None),
        ("AI Literacy please", "ai_literacy", None),
        ("Can you re-teach Workflow Design?", "workflow_design", None),
        ("review module 2", "foundations", None),
        ("Go back to Thinking in Workflows, lesson 3", "process_mapping", 3),
    ])
    def test_a_module_named_or_numbered_is_chosen(self, message, module_id, lesson):
        choice = chosen_module(message, MODULES)
        assert choice is not None and choice[0] == module_id and choice[3] == lesson

    def test_the_title_wins_over_a_conflicting_number(self):
        assert chosen_module("module 5, no, from AI Literacy", MODULES)[0] == "ai_literacy"

    @pytest.mark.parametrize("message", [
        "1",  # the first of the offered options, not Module 1
        "I want to start certification from beginning.",
        "What does Foundations cover?",
        "I want to do the Workflow Design exercise",
        "Show my progress in AI Literacy",
        "Compare AI Literacy and Foundations",
    ])
    def test_other_messages_choose_nothing(self, message):
        assert chosen_module(message, MODULES) is None


def test_the_ticket_reply_that_repeats_the_options_is_sent_back():
    with pytest.raises(ModelRetry) as retry:
        require_chosen_module(_ctx("from 1 AI Literacy"), "Would you like to review completed modules or continue?")
    message = str(retry.value)
    assert 'module_id "ai_literacy"' in message and "lesson_number 1" in message
    assert "do not open a different module" in message


def test_opening_a_different_module_is_sent_back():
    with pytest.raises(ModelRetry, match="ai_literacy"):
        require_chosen_module(_ctx("from 1 AI Literacy", opened=["extraction_engine"]),
                              "I cannot skip backward, so here is Extraction Engine.")


def test_opening_the_chosen_module_passes():
    reply = "Here's AI Literacy, Lesson 1."
    assert require_chosen_module(_ctx("from 1 AI Literacy", opened=["ai_literacy"]), reply) == reply


def test_sent_back_only_once_per_turn():
    ctx = _ctx("from 1 AI Literacy")
    with pytest.raises(ModelRetry):
        require_chosen_module(ctx, "Which would you like?")
    assert require_chosen_module(ctx, "Which would you like?") == "Which would you like?"


def test_module_titles_outside_a_course_conversation_are_ordinary_words():
    reply = "Here are some workflow design tips."
    assert require_chosen_module(_ctx("Let's start on Workflow Design for my grant", earlier_course_turn=False), reply) == reply


def test_validator_is_registered_and_prompt_allows_review():
    assert "require_chosen_module" in open(llm_service.__file__).read()
    prompt = llm_service.AGENTIC_CHAT_SYSTEM_PROMPT
    assert "including a completed one" in prompt and "never say you can't go back" in prompt
    assert "never write a lesson's text yourself" in prompt
