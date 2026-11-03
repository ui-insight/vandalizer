"""Feedback eligibility retains each concurrent onboarding observation."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.automation import Automation
from app.models.chat import ChatConversation
from app.models.document import SmartDocument
from app.models.knowledge import KnowledgeBase
from app.models.library import LibraryItem
from app.models.search_set import SearchSet
from app.models.team import TeamMembership
from app.models.workflow import Workflow
from app.routers import feedback_prompt
from app.services.certification_versions import readers


@pytest.mark.asyncio
async def test_feedback_eligibility_waits_for_all_onboarding_observations(monkeypatch):
    started = set()
    all_started = asyncio.Event()

    async def observation(name, value):
        started.add(name)
        if len(started) == 9:
            all_started.set()
        await all_started.wait()
        return value

    fixtures = [
        (SmartDocument, 'user_id', 'count', 2),
        (Workflow, 'user_id', 'to_list', [SimpleNamespace(num_executions=1)]),
        (SearchSet, 'user_id', 'count', 0),
        (LibraryItem, 'added_by_user_id', 'to_list', [SimpleNamespace(pinned=True, favorited=False)]),
        (TeamMembership, 'user_id', 'count', 2),
        (Automation, 'user_id', 'to_list', [SimpleNamespace(enabled=False)]),
        (KnowledgeBase, 'user_id', 'to_list', [SimpleNamespace(status='ready')]),
        (ChatConversation, 'user_id', 'count', 1),
    ]
    for model, field, method, value in fixtures:
        monkeypatch.setattr(model, field, field, raising=False)

        async def read(name=model.__name__, result=value):
            return await observation(name, result)

        query = SimpleNamespace(**{method: read})
        monkeypatch.setattr(model, 'find', lambda *args, result=query, **kwargs: result)

    async def certified(user_id):
        assert user_id == 'learner'
        return await observation('certification', True)

    monkeypatch.setattr(readers, 'has_earned_certification', certified)
    evaluate = AsyncMock(return_value={'slug': 'first-success'})
    monkeypatch.setattr(feedback_prompt.svc, 'evaluate_eligible_prompt', evaluate)
    user = SimpleNamespace(user_id='learner', is_demo_user=True)
    result = await asyncio.wait_for(feedback_prompt.get_pending_prompt(user), timeout=5)
    assert result == {'prompt': {'slug': 'first-success'}}
    evaluate.assert_awaited_once_with(user, {
        'has_documents': True, 'has_workflows': True, 'has_run_workflow': True,
        'has_extraction_sets': False, 'has_library_items': True,
        'has_pinned_item': True, 'has_favorited_item': False,
        'has_team_members': True, 'has_automations': True,
        'has_enabled_automation': False, 'has_knowledge_base': True,
        'has_ready_knowledge_base': True, 'has_chatted_with_docs': True,
        'is_certified': True,
    })
