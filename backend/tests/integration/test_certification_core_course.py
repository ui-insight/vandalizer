"""Exercise the Core credential over HTTP using a disposable database and synthetic chat turns."""
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from beanie import init_beanie
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.activity import ActivityEvent
from app.models.certification import CertificationProgress
from app.models.chat import ChatConversation, ChatMessage, ChatRole
from app.models.project import Project, ProjectJoinLink
from app.models.user import User
from app.routers.certification import router
from app.schemas.skills import SkillSnapshot
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.scenario_submissions import module_bank
from tests.integration import test_certification_release_rehearsal as rehearsal

repo = rehearsal.repo
pytestmark = rehearsal.pytestmark


async def test_core_graduates_from_its_own_work_sample_without_builder_credit(repo, tmp_path, monkeypatch):
    staging = tmp_path / 'core-qa'
    rehearsal.stage.prepare(staging)
    rehearsal.deploy(monkeypatch, staging)
    rehearsal.stage.publish_qa(staging, inventory=await rehearsal.observed_inventory(), reason='Core QA', actor='test')
    repo.catalog = CourseCatalog(staging)
    await init_beanie(database=CertificationProgress.get_motor_collection().database,
                      document_models=[ActivityEvent, ChatConversation, ChatMessage, ProjectJoinLink])
    user = await User(user_id='core-learner', name='Core Learner', email='core@example.test').insert()
    learner = await repo.ensure_initial(user.user_id)
    package = repo.catalog.load(learner.course_version)
    assert package.manifest.course_id == 'vandalizer-core'
    project = await Project(uuid=uuid4().hex, title='Cedar Creek CC-17', owner_user_id=user.user_id, root_folder_uuid='case').insert()
    chat = await ChatConversation(uuid=uuid4().hex, user_id=user.user_id, title='Cedar Creek case').insert()
    await ActivityEvent(type='conversation', user_id=user.user_id, project_uuid=project.uuid, conversation_id=chat.uuid).insert()
    # Synthetic versions of the assigned documents and the server's persisted turns.
    await repo.progress.update_one({'user_id': user.user_id}, {'$set': {
        'modules.core_chat.provisioned_docs': ['award-doc'], 'modules.core_knowledge.provisioned_docs': ['policy-doc']}})
    await chat.add_message(ChatRole.USER, 'How much does CC-17 authorize?', source_documents=[{'uuid': 'award-doc'}])
    await chat.add_message(ChatRole.ASSISTANT, 'The award authorizes $48,000.')
    chat.active_skill = SkillSnapshot(uuid='skill', version='1', title='Source check', instructions='Verify every source.')
    await chat.add_message(ChatRole.ASSISTANT, 'Review the policy passage.', tool_results=[{
        'tool_name': 'search_knowledge_base', 'content': [{'document_uuid': 'policy-doc',
        'content': 'Obtain written approval before booking travel.'}]}])
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user.user_id)
    monkeypatch.setattr('app.services.certification_service._fire_certification_complete_hooks', AsyncMock())
    params = {'enrollment_id': learner.uuid}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/certification/course', params=params)
        assert response.status_code == 200, response.text
        modules = response.json()['modules']
        assert [m['id'] for m in modules] == ['core_chat', 'core_projects', 'core_knowledge', 'core_skills', 'core_browser', 'core_case']
        for module in modules:
            mid = module['id']
            for lesson in module['lessons']:
                opened = await client.post('/certification/lessons/read', params=params, json={'module_id': mid, 'lesson_id': lesson['id']})
                assert opened.status_code == 200, opened.text
            bank = module_bank(package, mid)
            answers = {q.id: q.correct_choice_id for q in bank.questions}
            body = {'request_id': uuid4().hex, 'bank_sha256': bank.digest, 'answers': answers}
            endpoint = f'/certification/modules/{mid}/scenarios'
            if mid == 'core_case':
                assert await CredentialRepository().for_enrollment(user.user_id, learner.uuid) is None
                assert (await client.post(endpoint, params=params, json=body)).status_code == 409
                body['work_sample'] = {'project_id': project.uuid, 'conversation_id': chat.uuid}
                project.context = '\n'.join(next(c.text for c in q.choices if c.id == answers[q.id]) for q in bank.questions)
                await project.save()
                missing = await client.post(endpoint, params=params, json=body)
                assert missing.status_code == 422 and 'IANA' in missing.json()['detail']['message']
                assert missing.json()['detail']['code'] == 'work_sample_incomplete'
                await chat.add_message(ChatRole.ASSISTANT, 'Verified the contact domain.', tool_results=[
                    {'tool_name': 'record_value', 'content': {'recorded': True, 'value': 'example.org',
                     'url': 'https://www.iana.org/help/example-domains'}},
                    {'tool_name': 'browser_finish', 'content': {'ok': True, 'working_tab': 'closed'}}])
                foreign = {**body, 'work_sample': {**body['work_sample'], 'project_id': 'another-project'}}
                assert (await client.post(endpoint, params=params, json=foreign)).status_code == 422
                invite = await ProjectJoinLink(project_uuid=project.uuid, token=uuid4().hex, created_by=user.user_id,
                    expires_at=datetime.datetime.now() + datetime.timedelta(hours=1)).insert()
                shared = await client.post(endpoint, params=params, json=body)
                assert shared.status_code == 422 and 'unshared' in shared.text
                invite.revoked = True
                await invite.save()
            saved = await client.post(endpoint, params=params, json=body)
            assert saved.status_code == 200 and saved.json()['result']['passed'], saved.text
            if mid == 'core_case':
                project.context = 'edited after grading'
                await project.save()
                replay = await client.post(endpoint, params=params, json=body)
                assert replay.json() == saved.json()
                revised = await client.post(endpoint, params=params, json={**body, 'request_id': uuid4().hex})
                assert revised.status_code == 422 and 'four selected lines' in revised.text
            complete = await client.post(f'/certification/modules/{mid}/complete',
                params={**params, 'expected_attempts': 0, 'request_id': uuid4().hex},
                json={'consent': 'complete_selected_saved_outcomes', 'scenario_attempt_id': saved.json()['attempt_id']})
            assert complete.status_code == 200 and complete.json()['xp_earned'] == module['xp'], complete.text
    credential = await CredentialRepository().for_enrollment(user.user_id, learner.uuid)
    assert credential.credential_title == 'Vandalizer Core (QA staging)'
    assert len(credential.outcomes) == 9
