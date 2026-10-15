"""Course entry (CHAT-03): every entry message reaches the learner's own course and next action.

The Start, Continue and Review messages are what the home CTA, rail badge,
account menu, /certification URL and card action links send
(frontend/src/lib/certificationChat.ts). The real agentic chat agent, its
output validators and the real progress tool run against new, active and
certified enrollments in the authored 5.0 course. A scripted model first
answers generically, as a model that skips the tools would; the course-entry
validator must send that back, and the reply that follows is built from what
the progress tool returned.
"""
import json
import re
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.models.user import User
from app.services import llm_service
from app.services.access_control import TeamAccessContext
from app.services.approval_claims import COURSE_ENTRY_MESSAGES
from app.services.certification_versions import enrollments, module_readiness, readers, runtime
from app.services.certification_versions.catalog import CourseCatalog
from app.services.chat_deps import AgenticChatDeps
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

repo = base.repo
pytestmark = base.pytestmark
FRONTEND = Path(__file__).parents[3] / 'frontend/src/lib/certificationChat.ts'
ENTRY = dict(re.findall(r"export const (\w+)_CERTIFICATION_MESSAGE = '([^']+)'", FRONTEND.read_text()))
GENERIC = 'Certification is a great way to build skills! Explore the modules at your own pace.'


def scripted_model(requests):
    """Generic first, then the progress tool, then a reply built only from its result."""
    def respond(messages, info):
        requests.append(messages[-1].parts)
        returned = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if returned:
            result = returned[-1].content
            nxt = 'graduated' if result['certified'] else f"next: {result['next_module_id']}"
            return ModelResponse(parts=[TextPart(f"{result['course_title']} ({result['course_version']}), {nxt}")])
        if any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
            return ModelResponse(parts=[ToolCallPart('get_certification_progress', {})])
        return ModelResponse(parts=[TextPart(GENERIC)])
    return FunctionModel(function=respond)


async def enrolled(repo, monkeypatch, tmp_path, user_id):
    authored = candidate.__wrapped__(tmp_path)
    path = authored.folder.parent / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    path.write_text(json.dumps(registry))
    repo.catalog = CourseCatalog(authored.folder.parent)
    for module in (readers, runtime, enrollments, module_readiness):
        monkeypatch.setattr(module, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    user = await User(user_id=user_id, name='Synthetic Entry Learner', email=f'{user_id}@example.test').insert()
    return user, await repo.ensure_initial(user_id)


def test_backend_recognises_every_frontend_entry_message():
    assert set(ENTRY) == {'START', 'CONTINUE', 'REVIEW'}
    assert set(ENTRY.values()) == COURSE_ENTRY_MESSAGES


@pytest.mark.parametrize('entry', ['START', 'CONTINUE', 'REVIEW'])
@pytest.mark.parametrize('state', ['new', 'active', 'certified'])
async def test_entry_reaches_the_enrolled_course_and_its_next_action(repo, monkeypatch, tmp_path, state, entry):
    user, learner = await enrolled(repo, monkeypatch, tmp_path, f'entry-{state}-{entry.lower()}')
    order = [module.id for module in repo.catalog.load(VERSION).manifest.modules]
    progress = await repo.read_progress(user.user_id, learner.uuid)
    if state == 'active':
        await repo.progress.update_one({'_id': progress.id}, {'$set': {f'modules.{order[0]}.completed': True}})
    elif state == 'certified':
        await repo.progress.update_one({'_id': progress.id}, {'$set': {
            'certified': True, **{f'modules.{module_id}.completed': True for module_id in order}}})

    requests = []
    monkeypatch.setattr(llm_service, 'get_agent_model', lambda *a, **k: scripted_model(requests))
    llm_service._agentic_chat_agent_cache.clear()
    try:
        agent = llm_service.create_agentic_chat_agent('scripted-entry-model', system_config_doc={})
        deps = AgenticChatDeps(user=user, user_id=user.user_id, team_id=None, team_access=TeamAccessContext(),
                               organization_id=None, system_config_doc={}, model_name='scripted-entry-model',
                               turn_marker=0, user_message=ENTRY[entry])
        result = await agent.run(ENTRY[entry], deps=deps, instructions=llm_service.AGENTIC_CHAT_SYSTEM_PROMPT)
    finally:
        llm_service._agentic_chat_agent_cache.clear()

    # The generic reply was sent back, not delivered as the course's answer.
    assert any(isinstance(part, RetryPromptPart) for part in requests[1])
    assert GENERIC not in result.output
    returned = [part.content for message in result.new_messages() for part in message.parts
                if isinstance(part, ToolReturnPart) and part.tool_name == 'get_certification_progress']
    assert len(returned) == 1 and returned[0]['course_version'] == VERSION
    assert returned[0]['enrollment_id'] == learner.uuid
    expected = {'new': f'next: {order[0]}', 'active': f'next: {order[1]}', 'certified': 'graduated'}[state]
    assert result.output == f"{returned[0]['course_title']} ({VERSION}), {expected}"
    assert returned[0]['certified'] is (state == 'certified')
