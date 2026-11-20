"""'Check my module' runs the module check, never the module's workflow.

Support ticket: asked to "check my Advanced Nodes module", chat read the
module card, said "the certification data doesn't provide a pass/fail
checklist", and staged a Run workflow approval. On Module 4 it ran the
extraction. The check reads saved work and returns pass/fail per requirement.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.runtime import CourseOperation, _operation

VERSION = 'legacy-2026-10-02.1'


@pytest.mark.asyncio
async def test_practical_module_card_points_at_the_module_check(monkeypatch):
    from app.services import certification_service
    from app.services.chat_tools import get_certification_module

    package = CourseCatalog().load(VERSION, preview=True)
    token = _operation.set(CourseOperation('user1', package, SimpleNamespace(enrollment_id='a' * 32), False))
    monkeypatch.setattr(certification_service, 'get_progress_dict', AsyncMock(return_value={'modules': {}}))
    try:
        card = await get_certification_module(SimpleNamespace(deps=SimpleNamespace(user_id='user1')), 'advanced_nodes')
    finally:
        _operation.reset(token)

    assert card.get('error') is None
    assert card['assessment_mode'] == 'legacy_practical'
    assert 'check_certification_module' in card['module_check']
    assert 'without running anything' in card['module_check']


def test_check_tool_says_it_runs_nothing_and_covers_practical_modules():
    from app.services.chat_tools import check_certification_module

    doc = inspect.getdoc(check_certification_module)
    assert 'legacy_practical' in doc
    assert 'runs nothing' in doc
    assert 'never run a workflow' in doc


def test_prompt_routes_check_requests_to_the_check():
    from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT

    assert 'When the learner asks to check a legacy module' in AGENTIC_CHAT_SYSTEM_PROMPT
    assert 'do not run a workflow or extraction to check a module' in AGENTIC_CHAT_SYSTEM_PROMPT
