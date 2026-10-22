"""Lessons read in chat or the lesson card are recorded, and chat walks the
learner through the unread ones before the exercise.

Support ticket: chat skipped from Module 0's lesson 1 to the reflection
questions, offered "Jump to the exercise" in Module 1, and re-sent all six
lessons the learner had read with the card's Next lesson.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

from app.services import certification_service as svc
from app.services.approval_claims import require_lessons_in_order

LESSONS = {"lessons": [{"id": f"m.l{n}", "title": f"L{n}", "content": "c"} for n in range(1, 7)]}


@pytest.fixture
def course():
    with patch.object(svc, "get_lessons", return_value=LESSONS), \
         patch.object(svc, "course_module_xp", return_value={"foundations": 50}):
        yield


def test_reading_is_reported_by_lesson_number(course):
    assert svc.lesson_reading("foundations", ["m.l1", "m.l3", "elsewhere"]) == {
        "lessons_read": [1, 3], "unread_lessons": [2, 4, 5, 6],
    }


@pytest.mark.asyncio
async def test_marking_adds_only_new_lessons_of_the_module(course):
    prog = SimpleNamespace(id="p1", lessons_read={"foundations": ["m.l1"]})
    collection = MagicMock(update_one=AsyncMock())
    with patch.object(svc, "get_progress", AsyncMock(return_value=prog)), \
         patch.object(svc.CertificationProgress, "get_motor_collection", return_value=collection):
        read = await svc.mark_lessons_read("u1", "foundations", ["m.l1", "m.l2", "not-a-lesson"])
    assert read == ["m.l1", "m.l2"]
    collection.update_one.assert_awaited_once_with(
        {"_id": "p1"}, {"$addToSet": {"lessons_read.foundations": {"$each": ["m.l2"]}}},
    )


@pytest.mark.asyncio
async def test_marking_never_breaks_a_lesson(course):
    with patch.object(svc, "get_progress", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await svc.mark_lessons_read("u1", "foundations", ["m.l2"]) == ["m.l2"]


def _ctx(output_unread, user_message="yes", tools=("get_certification_lesson",)):
    messages = [
        ModelRequest(parts=[UserPromptPart(content=user_message)]),
        ModelResponse(parts=[ToolCallPart(tool_name=t, args={}, tool_call_id=f"c{i}") for i, t in enumerate(tools)]),
        ModelRequest(parts=[ToolReturnPart(
            tool_name="get_certification_lesson", tool_call_id="c0",
            content={"module_id": "foundations", "lesson_number": 1, "unread_lessons": output_unread},
        )]),
    ]
    deps = SimpleNamespace(user_message=user_message, lesson_skip_retry_used=False)
    return SimpleNamespace(partial_output=False, deps=deps, messages=messages)


def test_skipping_to_the_exercise_with_lessons_unread_is_sent_back():
    with pytest.raises(ModelRetry, match="lesson 2"):
        require_lessons_in_order(_ctx([2, 3, 4]), "Want to jump to the exercise?")


def test_starting_an_assessment_tool_with_lessons_unread_is_sent_back():
    ctx = _ctx([2, 3], tools=("get_certification_lesson", "check_certification_module"))
    with pytest.raises(ModelRetry):
        require_lessons_in_order(ctx, "Let me check your work.")


@pytest.mark.parametrize("ctx,reply", [
    (_ctx([2, 3]), "Next up is lesson 2. Ready for lesson 2?"),
    (_ctx([]), "That was the last lesson. Want to jump to the exercise?"),
    (_ctx([2, 3], user_message="I know this already, skip to the exercise"), "Sure, let's jump to the exercise."),
])
def test_the_next_lesson_a_finished_module_or_a_requested_skip_pass(ctx, reply):
    assert require_lessons_in_order(ctx, reply) == reply


def test_sent_back_once_per_turn():
    ctx = _ctx([2, 3])
    with pytest.raises(ModelRetry):
        require_lessons_in_order(ctx, "Want to jump to the exercise?")
    assert require_lessons_in_order(ctx, "Want to jump to the exercise?") == "Want to jump to the exercise?"


@pytest.mark.asyncio
async def test_the_lesson_tool_records_the_lesson_and_reports_what_is_unread():
    from app.services.chat_tools import get_certification_lesson

    real = svc.get_lessons("foundations")["lessons"]
    ctx = MagicMock()
    ctx.deps = SimpleNamespace(user_id="user1", user=MagicMock(user_id="user1"), team_id=None)
    marked = AsyncMock(return_value=[real[0]["id"], real[1]["id"]])
    with patch.object(svc, "mark_lessons_read", marked):
        result = await get_certification_lesson(ctx, "foundations", 2)
    marked.assert_awaited_once_with("user1", "foundations", [real[1]["id"]])
    assert result["lessons_read"] == [1, 2]
    assert result["unread_lessons"] == list(range(3, len(real) + 1))
