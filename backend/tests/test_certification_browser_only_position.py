"""Lesson position on a course whose place isn't saved on the server.

Support ticket: on the older, unversioned course, after Next lesson chat
called save_certification_position; it failed ("This saved course requires
versioned certification support") with Review recovery options, and chat said
the place was "still saved automatically". On that course only the lesson
card's Save my place keeps the place, in that browser.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import chat_tools


def _context():
    return SimpleNamespace(deps=SimpleNamespace(user_id="learner", user=SimpleNamespace(user_id="learner")))


@pytest.mark.asyncio
async def test_saving_a_place_on_an_unversioned_course_is_not_an_error():
    versioned = AsyncMock()
    with patch("app.services.certification_versions.runtime.versioning_enabled", return_value=False), \
         patch.object(chat_tools, "_save_certification_position_versioned", versioned):
        out = await chat_tools.save_certification_position(_context(), "ai_literacy", "l2", 0, "made-up-enrollment")
    assert "error" not in out
    assert out["saved"] is False and out["status"] == "not_supported"
    assert out["position_saving"] == "this_browser_only"
    assert "only in this browser" in out["assistant_instruction"]
    versioned.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_versioned_course_still_saves_on_the_server():
    versioned = AsyncMock(return_value={"saved": True, "position_revision": 2})
    with patch("app.services.certification_versions.runtime.versioning_enabled", return_value=True), \
         patch.object(chat_tools, "_save_certification_position_versioned", versioned):
        out = await chat_tools.save_certification_position(_context(), "ai_literacy", "l2", 1, "enr-1")
    assert out == {"saved": True, "position_revision": 2}
    versioned.assert_awaited_once()


@pytest.mark.asyncio
async def test_progress_on_an_unversioned_course_says_the_place_is_browser_only():
    from app.services import certification_service as cert_svc

    prog = {"modules": {}, "total_xp": 0, "level": "novice", "certified": False}
    with patch("app.services.certification_versions.runtime.versioning_enabled", return_value=False), \
         patch.object(cert_svc, "get_progress_dict", AsyncMock(return_value=prog)):
        out = await chat_tools.get_certification_progress(_context())
    assert "error" not in out, out
    assert out["position_saving"] == "this_browser_only"
    assert "Don't call save_certification_position" in out["position_note"]
    assert "position_revision" not in out


def test_chat_is_told_not_to_save_or_claim_a_server_place():
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT as prompt

    assert "Call it only when progress returned position_revision" in prompt
    assert "kept only in this browser" in prompt
    assert "Don't call a lesson locked unless a tool result says it can't be opened" in prompt
