"""The guided course in chat follows the app's order, not the model's reading
of the rules: lessons in order, then the exercise, lab, answers, check and
completion.

Support ticket: on two models the same module ran differently: lessons
skipped, offered as "jump to the exercise", or all pushed at once.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import certification_service as svc

LESSONS = {"lessons": [{"id": f"m.l{n}", "title": f"L{n}", "content": "c"} for n in range(1, 7)]}


@pytest.fixture
def course():
    with patch.object(svc, "get_lessons", return_value=LESSONS), \
         patch.object(svc, "course_module_xp", return_value={"foundations": 50, "ai_literacy": 50}), \
         patch.object(svc, "course_module_order", return_value=["ai_literacy", "foundations"]), \
         patch.object(svc, "course_module_titles", return_value={"foundations": "Foundations", "ai_literacy": "AI Literacy"}):
        yield


def _prog(read=(), module=None, unlocked=False, position=None):
    return SimpleNamespace(
        id="p1", unlocked=unlocked, learning_position=position,
        lessons_read={"foundations": list(read)}, modules={"foundations": module or {}},
    )


async def _gate(prog):
    with patch.object(svc, "get_progress", AsyncMock(return_value=prog)):
        return await svc.lesson_gate("u1", "foundations")


@pytest.mark.asyncio
async def test_unread_lessons_gate_the_module(course):
    gate = await _gate(_prog(read=["m.l1", "m.l2"]))
    assert gate["next_lesson"] == 3
    assert gate["unread_lessons"] == [3, 4, 5, 6]
    assert gate["lesson_count"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("prog", [
    _prog(read=[f"m.l{n}" for n in range(1, 7)]),           # all read
    _prog(unlocked=True),                                    # admin-unlocked
    _prog(module={"provisioned_docs": ["d1"]}),              # already under way
    _prog(module={"self_assessment": {"q": "a"}}),
    _prog(module={"attempts": 1}),
    _prog(module={"completed": True}),
])
async def test_no_gate_when_read_unlocked_or_already_under_way(course, prog):
    assert await _gate(prog) is None


@pytest.mark.asyncio
async def test_an_unreadable_progress_never_strands_the_learner(course):
    with patch.object(svc, "get_progress", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await svc.lesson_gate("u1", "foundations") is None


def _ctx():
    ctx = MagicMock()
    ctx.deps = SimpleNamespace(user_id="u1", user=MagicMock(user_id="u1"), team_id=None)
    return ctx


GATE = {"lessons_read": [1], "unread_lessons": [2, 3, 4, 5, 6], "next_lesson": 2, "lesson_count": 6}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [
    ("check_certification_module", ()),
    ("provision_certification_lab", ()),
    ("submit_certification_assessment", ({"q": "a"},)),
    ("complete_certification_module", ()),
])
async def test_course_steps_refuse_until_the_lessons_are_read(tool, args):
    from app.services import chat_tools

    with patch.object(svc, "lesson_gate", AsyncMock(return_value=GATE)):
        result = await getattr(chat_tools, tool)(_ctx(), "foundations", *args)
    assert result["code"] == "lessons_first"
    assert "next is lesson 2 of 6" in result["error"]


@pytest.mark.asyncio
async def test_lessons_are_taught_in_order():
    from app.services.chat_tools import get_certification_lesson

    real = svc.get_lessons("foundations")["lessons"]
    gate = {**GATE, "lesson_count": len(real)}
    with patch.object(svc, "lesson_gate", AsyncMock(return_value=gate)), \
         patch.object(svc, "mark_lessons_read", AsyncMock(return_value=[real[0]["id"]])):
        skipped = await get_certification_lesson(_ctx(), "foundations", 4)
        assert skipped["code"] == "lessons_first"
        assert "lesson 2" in skipped["error"]
        assert (await get_certification_lesson(_ctx(), "foundations", 2))["lesson_number"] == 2
        assert (await get_certification_lesson(_ctx(), "foundations", 1))["lesson_number"] == 1  # review


@pytest.mark.asyncio
async def test_the_step_follows_the_saved_position_then_course_order(course):
    position = {"module_id": "foundations", "lesson_id": "m.l2"}
    prog = SimpleNamespace(**{**vars(_prog(read=["m.l1"], position=position)), "modules": {"ai_literacy": {}}})
    with patch.object(svc, "get_progress", AsyncMock(return_value=prog)):
        step = await svc.guided_step("u1")
    assert step["module_id"] == "foundations"
    assert step["gate"]["next_lesson"] == 3  # the saved lesson 2 counts as reached

    prog.learning_position = None
    with patch.object(svc, "get_progress", AsyncMock(return_value=prog)):
        assert (await svc.guided_step("u1"))["module_id"] == "ai_literacy"


def test_the_step_block_names_the_next_lesson_or_the_exercise():
    block = svc.guided_step_block({"title": "Foundations", "gate": GATE})
    assert "lesson 2 of 6 is next" in block and "refuse" in block
    done = svc.guided_step_block({"title": "Foundations", "gate": None})
    assert "lessons done" in done and "one per turn" in done
    assert svc.guided_step_block(None) == ""


@pytest.mark.asyncio
async def test_the_saved_place_counts_as_reached(course):
    gate = await _gate(_prog(read=["m.l1"], position={"module_id": "foundations", "lesson_id": "m.l4"}))
    assert gate["next_lesson"] == 5
