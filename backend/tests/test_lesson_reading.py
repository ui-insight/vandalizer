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
async def test_the_lesson_tool_reports_what_is_unread_and_opening_does_not_read_a_checked_lesson():
    from app.services.chat_tools import get_certification_lesson

    real = svc.get_lessons("foundations")["lessons"]
    ctx = MagicMock()
    ctx.deps = SimpleNamespace(user_id="user1", user=MagicMock(user_id="user1"), team_id=None)
    marked = AsyncMock(return_value=[real[0]["id"], real[1]["id"]])
    with patch.object(svc, "mark_lessons_read", marked):
        result = await get_certification_lesson(ctx, "foundations", 2)
    # Lesson 2 has a knowledge check: opening it records nothing new.
    marked.assert_awaited_once_with("user1", "foundations", [])
    assert result["check_required"] is True
    assert result["lessons_read"] == [1, 2]
    assert result["unread_lessons"] == list(range(3, len(real) + 1))


# Mandatory lesson checks. Support ticket: clicking Next lesson through a
# module "read" all six lessons in seconds; opening a lesson counted as reading.
CHECKED = {"lessons": [
    {"id": f"m.l{n}", "title": f"L{n}", "content": "c", "knowledge_check": {"question": "Q?", "options": [
        {"text": "right", "correct": True, "explanation": "Because the lesson says so."},
        {"text": "wrong", "correct": False, "explanation": "The lesson says otherwise."},
    ]}} for n in range(1, 4)
]}


@pytest.fixture
def checked_course():
    with patch.object(svc, "get_lessons", return_value=CHECKED), \
         patch.object(svc, "course_module_xp", return_value={"foundations": 50}):
        yield


@pytest.mark.asyncio
async def test_opening_a_checked_lesson_does_not_read_it(checked_course):
    marked = AsyncMock(return_value=[])
    with patch.object(svc, "mark_lessons_read", marked):
        await svc.record_lessons_opened("user1", "foundations", ["m.l1"])
    marked.assert_awaited_once_with("user1", "foundations", [])


@pytest.mark.asyncio
async def test_a_wrong_answer_explains_and_reads_nothing(checked_course):
    marked = AsyncMock(return_value=[])
    with patch.object(svc, "lesson_gate", AsyncMock(return_value={"next_lesson": 1, "lesson_count": 3})), \
         patch.object(svc, "mark_lessons_read", marked):
        result = await svc.answer_lesson_check("user1", "foundations", "m.l1", 1)
    assert result["correct"] is False
    assert result["explanation"] == "The lesson says otherwise."
    marked.assert_awaited_once_with("user1", "foundations", [])  # only the read-back


@pytest.mark.asyncio
async def test_a_correct_answer_reads_the_lesson(checked_course):
    marked = AsyncMock(return_value=["m.l1"])
    with patch.object(svc, "lesson_gate", AsyncMock(return_value={"next_lesson": 1, "lesson_count": 3})), \
         patch.object(svc, "mark_lessons_read", marked):
        result = await svc.answer_lesson_check("user1", "foundations", "m.l1", 0)
    assert result["correct"] is True
    marked.assert_awaited_once_with("user1", "foundations", ["m.l1"])
    assert result["unread_lessons"] == [2, 3]


@pytest.mark.asyncio
async def test_checks_are_answered_in_order(checked_course):
    with patch.object(svc, "lesson_gate", AsyncMock(return_value={"next_lesson": 1, "lesson_count": 3})):
        result = await svc.answer_lesson_check("user1", "foundations", "m.l3", 0)
    assert "pass lesson 1 first" in result["error"]


@pytest.mark.asyncio
async def test_an_answer_outside_the_options_is_refused(checked_course):
    with patch.object(svc, "lesson_gate", AsyncMock(return_value=None)):
        result = await svc.answer_lesson_check("user1", "foundations", "m.l1", 5)
    assert "error" in result


@pytest.mark.asyncio
async def test_a_saved_place_does_not_read_checked_lessons(checked_course):
    prog = SimpleNamespace(modules={}, unlocked=False, lessons_read={},
                           learning_position={"module_id": "foundations", "lesson_id": "m.l3"})
    with patch.object(svc, "get_progress", AsyncMock(return_value=prog)):
        gate = await svc.lesson_gate("user1", "foundations")
    assert gate["next_lesson"] == 1


def test_checks_are_required_except_for_unlocked_or_started_modules(checked_course):
    fresh = SimpleNamespace(modules={}, unlocked=False)
    started = SimpleNamespace(modules={"foundations": {"attempts": 1}}, unlocked=False)
    assert svc.lesson_checks_required(fresh) == {"foundations": True}
    assert svc.lesson_checks_required(started) == {"foundations": False}
    assert svc.lesson_checks_required(SimpleNamespace(modules={}, unlocked=True)) == {"foundations": False}
