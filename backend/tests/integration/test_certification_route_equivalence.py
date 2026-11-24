"""Equivalent work earns the same assessment whichever route built it.

GRADE-12: grading reads saved owned artifacts, never the route that made
them. Build the same assessed extraction in the editor and through the chat
tool (refined in the editor, the supported mixed route), then capture, test
and run both and compare everything that reaches the checks.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from beanie import init_beanie
import pytest

from app.database import ALL_MODELS
from app.dependencies import get_current_user
from app.models.search_set import SearchSet
from app.models.user import User
from app.routers.extractions import router as extraction_router
from app.services.certification_versions import validation_delivery
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_http as http
from tests.integration import test_certification_validation_suites as suites
from tests.test_chat_tools import _make_context

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
IDENTITY = {'uuid', 'title', 'id'}


def comparable(artifact):
    """What the checks can see, minus the identities two artifacts never share."""
    return {**{key: value for key, value in artifact.items() if key not in IDENTITY},
            'fields': [{key: value for key, value in field.items() if key not in IDENTITY} for field in artifact['fields']]}


def without_identity_hash(value):
    """Record digests cover each record's own uuid, title or run, so they differ by identity alone."""
    if isinstance(value, dict):
        return {key: without_identity_hash(item) for key, item in value.items() if key not in ('artifact_sha256', 'result_sha256')}
    if isinstance(value, list):
        return [without_identity_hash(item) for item in value]
    return value


async def editor_route(client, fields):
    created = await client.post('/api/extractions/search-sets', json={'title': 'Editor route extraction'})
    assert created.status_code == 200, created.text
    uuid = created.json()['uuid']
    for field in fields:
        item = await client.post(f'/api/extractions/search-sets/{uuid}/items',
                                 json={'title': field.title, 'searchphrase': field.searchphrase})
        assert item.status_code == 200, item.text
    return uuid


async def chat_route(client, f, fields):
    from app.services.chat_tools import create_extraction_from_document
    ctx = _make_context(user_id=f.learner.user_id, team_id=None, user=MagicMock(user_id=f.learner.user_id))
    # Field discovery is the only model call; it proposes the names, as chat does.
    with patch('app.services.search_set_service.suggest_fields_from_documents',
               new=AsyncMock(return_value=([field.title for field in fields], 'Suggested'))):
        created = await create_extraction_from_document(ctx, [f.documents[0].uuid], title='Chat route extraction', confirmed=True)
    assert created.get('field_count') == len(fields), created
    uuid = created['extraction_set_uuid']
    items = (await client.get(f'/api/extractions/search-sets/{uuid}/items')).json()
    # Chat seeds each instruction with the field name; the learner refines it in the editor.
    assert [item['searchphrase'] for item in items] == [field.title for field in fields]
    for item, field in zip(items, fields):
        changed = await client.patch(f'/api/extractions/items/{item["id"]}', json={'searchphrase': field.searchphrase})
        assert changed.status_code == 200, changed.text
    return uuid


async def test_editor_and_chat_built_extractions_receive_the_same_checks(versioned_runtime, monkeypatch):
    f = await http.fixture(versioned_runtime, monkeypatch)
    f.app.dependency_overrides[get_current_user] = lambda: User(user_id=f.learner.user_id)
    f.app.include_router(extraction_router, prefix='/api/extractions')
    # The editor's create reply reads quality and portability collections, so
    # this disposable database registers every app model, as the app does.
    await init_beanie(database=SearchSet.get_motor_collection().database, document_models=ALL_MODELS)
    params = {'enrollment_id': f.learner.uuid}
    engine_inputs = {}
    async with f.client as client:
        routes = {'editor': await editor_route(client, f.fields), 'chat_then_editor': await chat_route(client, f, f.fields)}
        results = {}
        for route, artifact_id in routes.items():
            captured = await http.post(client, 'modules/validation_qa/validation-captures', params,
                                       {**f.body, 'request_id': uuid4().hex, 'artifact_id': artifact_id})
            snapshot = await validation_delivery.ValidationInputRepository().get(f.learner.user_id, captured['uuid'])
            suite = await http.post(client, 'modules/validation_qa/validation-suites', params, suites.request(f, snapshot))
            f.provider.reset_mock()
            run = await http.plan_and_run(f, client, params, captured, suite)
            engine_inputs[route] = [{key: call.kwargs[key] for key in ('field_metadata', 'doc_texts', 'model')}
                                    for call in f.provider.call_args_list]
            results[route] = (captured, run)
    (editor, editor_run), (mixed, mixed_run) = results['editor'], results['chat_then_editor']
    assert editor['artifact_id'] != mixed['artifact_id']
    assert comparable(editor['artifact']) == comparable(mixed['artifact'])
    assert editor['documents'] == mixed['documents']
    assert engine_inputs['editor'] == engine_inputs['chat_then_editor'] and len(engine_inputs['editor']) == 2
    checks = [without_identity_hash(run['result']['checks']) for run in (editor_run, mixed_run)]
    assert checks[0] == checks[1] and checks[0]['observed_semantic_failure']



async def test_a_chat_built_connected_workflow_captures_and_plans(repo):
    """Chat wires its format step to every earlier step; the connected lab must accept that route."""
    from app.services.chat_tools import create_workflow
    fixture = await base.connected_workflow_fixture(repo)
    source = fixture[0]
    ctx = _make_context(user_id=source.user_id, team_id=None, user=User(user_id=source.user_id), model_name='fixture-model')
    built = await create_workflow(ctx, 'Chat subaward chain', [
        {'name': 'Extract terms', 'type': 'extraction', 'extractions': ['Extract the subaward amount.']},
        {'name': 'Separate obligations', 'type': 'prompt', 'prompt': 'Separate source obligations from interpretation.'},
        {'name': 'Internal summary', 'type': 'format', 'format_template': 'Preserve the supported terms and unresolved questions.', 'is_output': True},
    ], confirmed=True)
    assert built.get('workflow_id'), built
    chat_fixture = (*fixture[:7], {**fixture[7], 'request_id': uuid4().hex, 'workflow_id': built['workflow_id']})
    snapshot = await base.capture_connected(repo, chat_fixture)
    prepared = await base.prepare_connected(repo, chat_fixture, base.connected_plan_body(snapshot))
    stages = prepared['plan']['stage_plans'] if 'plan' in prepared else prepared['stage_plans']
    assert [stage['task_type'] for stage in stages] == ['Extraction', 'Prompt', 'Formatter']
    assert stages[2]['effective_input_sources'] == ['earlier_steps'] and stages[2]['receives_previous_stage'] is True


async def test_one_design_survives_switching_from_chat_to_the_editor(repo):
    """M03-04: chat builds the design, the editor revises it, and both captures name one workflow and attempt."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.routers.workflows import router as workflow_router
    from app.services.certification_versions.workflow_design_inputs import WorkflowDesignInputRepository
    from app.services.chat_tools import create_workflow
    source, package, _, _, _, _, body = await base.workflow_design_capture_fixture(repo)
    await init_beanie(database=SearchSet.get_motor_collection().database, document_models=ALL_MODELS)
    user = User(user_id=source.user_id)
    ctx = _make_context(user_id=source.user_id, team_id=None, user=user, model_name='fixture-model')
    built = await create_workflow(ctx, 'Monthly comparison draft', [
        {'name': 'Compare reports', 'type': 'prompt', 'prompt': 'Compare the three assigned reports and cite every value.', 'is_output': True}], confirmed=True)
    assert built.get('workflow_id'), built
    request = {**body, 'workflow_id': built['workflow_id'], 'handoff': 'supplied_example', 'process_submission_id': None}
    first = await base.capture_workflow_design(repo, source, package, {**request, 'request_id': uuid4().hex})
    task_id = first['artifact']['steps'][0]['tasks'][0]['id']
    app = FastAPI()
    app.include_router(workflow_router, prefix='/api/workflows')
    app.dependency_overrides[get_current_user] = lambda: user
    revised_prompt = 'Compare the three assigned reports, cite every value and mark conflicts UNRESOLVED for the reviewer.'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        data = {**first['artifact']['steps'][0]['tasks'][0]['data'], 'prompt': revised_prompt}
        response = await client.patch(f'/api/workflows/tasks/{task_id}', json={'data': data})
        assert response.status_code == 200, response.text
    second = await base.capture_workflow_design(repo, source, package, {**request, 'request_id': uuid4().hex})
    assert second['artifact_id'] == first['artifact_id'] == built['workflow_id']
    assert second['enrollment_id'] == first['enrollment_id'] == source.uuid
    assert second['artifact']['steps'][0]['tasks'][0]['id'] == task_id
    assert second['artifact']['steps'][0]['tasks'][0]['data']['prompt'] == revised_prompt
    assert second['artifact_sha256'] != first['artifact_sha256']
    assert await WorkflowDesignInputRepository().get(source.user_id, first['uuid']) == first
