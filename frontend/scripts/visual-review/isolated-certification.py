"""Disposable certification API for browser integration QA; never a production server.

Run with backend/.venv/bin/python from any directory. Binds 127.0.0.1:5293,
uses a new certification_qa_browser_* database on MongoDB port 27028, and drops
that exact database on normal shutdown. Authentication and providers are test
substitutes; certification routes, repositories and persistence are real.
"""
# ruff: noqa: E402 -- isolate environment and sockets before importing the application.
from contextlib import asynccontextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

MODULE = sys.argv[1] if len(sys.argv) == 2 else 'foundations'
if MODULE not in ('foundations', 'extraction_engine', 'process_mapping', 'workflow_design', 'multi_step', 'advanced_nodes', 'output_delivery') or len(sys.argv) > 2:
    raise SystemExit('Usage: isolated-certification.py [foundations|extraction_engine|process_mapping|workflow_design|multi_step|advanced_nodes|output_delivery]')
ROOT = Path(__file__).resolve().parents[3]
RUN = Path(tempfile.mkdtemp(prefix='vandalizer-certification-browser-', dir='/private/tmp'))
os.chdir(RUN)
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.clear()
os.environ.update({'PATH': '/usr/bin:/bin', 'MONGO_HOST': 'mongodb://127.0.0.1:27028/',
                   'DISABLE_UPDATE_CHECK': 'true', 'TELEMETRY_ENABLED': 'false',
                   'PROMOTIONAL_EMAILS_ENABLED': 'false'})
# No inherited provider credentials, .env file, SMTP, cache or remote sockets.
original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

def permitted(address):
    if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', 'localhost', '::1') or address[1] != 27028:
        raise OSError('Certification QA permits outbound connections only to its disposable MongoDB')

def connect(sock, address):
    permitted(address)
    return original_connect(sock, address)

def connect_ex(sock, address):
    permitted(address)
    return original_connect_ex(sock, address)

socket.socket.connect, socket.socket.connect_ex = connect, connect_ex

from beanie import init_beanie
from bson import ObjectId
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import uvicorn

spec = importlib.util.spec_from_file_location('certification_browser_fixtures', ROOT / 'backend/tests/integration/test_certification_enrollments.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import automatic_review, practical_preparation, runtime
from app.services.certification_versions.learner_decisions import load_prompt
from app.services.extraction_engine import ExtractionEngine

state = {'extraction_calls': 0, 'judge_calls': 0}
patches = pytest.MonkeyPatch()

@asynccontextmanager
async def lifespan(app):
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27028', serverSelectionTimeoutMS=3000)
    database = 'certification_qa_browser_' + uuid4().hex
    names = ['CertificationEnrollment', 'CertificationEnrollmentSelection', 'CertificationProgress', 'CertificationCredential',
             'CertificationAttempt', 'CertificationRecoveryRecord', 'CertificationLabInput', 'CertificationScenarioAttempt',
             'CertificationLabExecution', 'CertificationReviewAttempt', 'CertificationLearnerDecision', 'CertificationProcessSubmission', 'CertificationWorkflowDesignSubmission', 'SmartDocument',
             'SearchSet', 'SearchSetItem', 'User', 'Workflow', 'WorkflowStep', 'WorkflowStepTask']
    try:
        await init_beanie(database=client[database], document_models=[getattr(fixtures, name) for name in names])
        shutil.copytree(fixtures.CATALOG_ROOT, RUN / 'courses')
        path = RUN / 'courses/registry.json'
        registry = json.loads(path.read_text())
        registry['releases'][fixtures.VERSION].update(state='published', supported_for_existing=True)
        registry.update(legacy_continuation=fixtures.VERSION, new_enrollment_default=fixtures.VERSION, transition_policy='optional')
        path.write_text(json.dumps(registry))
        repository = fixtures.EnrollmentRepository(fixtures.CourseCatalog(RUN / 'courses'))
        if MODULE == 'output_delivery':
            from tests.integration.test_certification_output_workflow_plan import fixture as output_fixture, RUNTIME
            from tests.test_certification_output_artifacts import record as output_record
            from app.services import workflow_engine
            output = await output_fixture(repository)
            source, package, document, storage = output.learner, output.package, output.document, output.storage
            await fixtures.CertificationLabInput.get_motor_collection().delete_many({})
            state.update(workflow_id=str(output.workflow.id), output_calls=0, output_config=RUNTIME, output_formatter=output.tasks[2])
            output.tasks[2].data['format_template'] = 'Original unstructured summary for QA repair'
            await output.tasks[2].save()
            def output_prompt(**kwargs):
                state['output_calls'] += 1
                return json.dumps(output_record())
            def output_format(model, instructions, context, **kwargs):
                state['output_calls'] += 1
                return 'Synthetic formatting', ('Unstructured prose instead of a CSV record' if 'unstructured' in instructions else output_record())
            patches.setattr(workflow_engine, 'llm_chat_model', output_prompt)
            patches.setattr(workflow_engine, 'format_model', output_format)
            artifact = snapshot = run = None
            required, entity, filename = [], {}, 'progress-report-year2.pdf'
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:7]
        elif MODULE == 'advanced_nodes':
            from tests.integration.test_certification_advanced_workflow_plan import fixture as budget_fixture, RUNTIME
            from app.services import workflow_engine
            budget = await budget_fixture(repository)
            source, package, document, storage = budget.learner, budget.package, budget.document, budget.storage
            await fixtures.CertificationLabInput.get_motor_collection().delete_many({})
            state.update(workflow_id=str(budget.workflow.id), budget_calls=0, budget_config=RUNTIME)
            def budget_provider(**kwargs):
                state['budget_calls'] += 1
                if kwargs['prompt'] == 'Write the internal memo':
                    return 'INTERNAL BUDGET MEMO — QA stub. Source additions and interpretation remain separate. The saved equipment result needs review. The narrative base, indirect estimate and period assumptions remain unresolved. No institutional policy was supplied.'
                return 'SOURCE REVIEW — QA stub: ' + kwargs['prompt'] + '. This result does not establish institutional approval.'
            patches.setattr(workflow_engine, 'llm_chat_model', budget_provider)
            artifact = snapshot = run = None
            required, entity, filename = [], {}, 'budget-justification.pdf'
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:6]
        elif MODULE == 'multi_step':
            import fitz
            from tests.test_certification_connected_workflow_runtime import providers
            fixture = await fixtures.connected_workflow_fixture(repository)
            source, package, document, workflow, steps, tasks, storage, capture_body = fixture
            with fitz.open(stream=package.read('documents/subaward-agreement.pdf'), filetype='pdf') as pdf:
                document.raw_text = '\n\n'.join(page.get_text() for page in pdf)
            await document.save()
            tasks[2].data['input_sources'] = ['workflow_documents']
            await tasks[2].save()
            stage_providers = providers(patches)
            stage_providers[1].return_value = 'Supported source obligations remain separate from interpretation. Institutional compliance is unresolved because no institutional policy was supplied.'
            stage_providers[2].side_effect = lambda model, instructions, context, **kwargs: ('Synthetic provider prompt', 'INTERNAL DRAFT\n' + (context if isinstance(context, str) else json.dumps(context)))
            state.update(workflow_id=str(workflow.id), formatter_task=tasks[2], stage_providers=stage_providers)
            artifact = snapshot = run = None
            required, entity, filename = [], {}, 'subaward-agreement.pdf'
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:5]
        elif MODULE == 'workflow_design':
            source, package, original_map, workflow, step, task, capture_body = await fixtures.workflow_design_capture_fixture(repository)
            document = artifact = snapshot = run = None
            required, entity, filename = [], {}, None
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:3]
            state['workflow_id'] = str(workflow.id)
        elif MODULE == 'process_mapping':
            source, package, case, _ = await fixtures.process_design_fixture(repository)
            document = artifact = snapshot = run = None
            required, entity, filename = [], {}, None
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:2]
        elif MODULE == 'extraction_engine':
            source, package, document, artifact, snapshot, run = await fixtures.extraction_repair_fixture(repository)
            required = load_prompt(package, MODULE, 'repair_values').required_fields
            expected = {'Total Budget': '1250000', 'Postdoctoral Fellow Name': None, 'Human Subjects': 'No', 'Vertebrate Animals': 'Yes'}
            entity = {field['searchphrase']: expected[field['title']] for field in snapshot['artifact']['fields']}
            filename = 'nih-r01-neuroscience.pdf'
            prerequisites = [item.id for item in package.manifest.modules if item.id != MODULE][:4]
        else:
            source, package, document, snapshot, run = await fixtures.learner_decision_fixture(repository, with_proposal=True)
            artifact = await fixtures.SearchSet.find_one({'uuid': snapshot['artifact_id']})
            await fixtures.SearchSetItem.find({'searchset': artifact.uuid}).delete()
            required = load_prompt(package, MODULE, 'value_review').required_fields
            for field in required:
                await fixtures.SearchSetItem(searchset=artifact.uuid, user_id=source.user_id, searchphrase=field, searchtype='extraction').insert()
            document.raw_text = 'Synthetic QA source. PI Name: Sarah Chen. Institution: University of Idaho. Total Budget: USD 485000. Project Period: 2026–2028. Sponsoring Agency: National Science Foundation.'
            await document.save()
            entity = {'PI Name': 'Sarah Chen', 'Institution': 'University of Idaho', 'Total Budget': 'USD 485000',
                      'Project Period': '2026–2028', 'Sponsoring Agency': 'National Science Foundation'}
            filename = 'nsf-proposal-alpine-ecology.pdf'
            prerequisites = ['ai_literacy']
        # Remove only this fixture's seed records in its disposable database.
        if snapshot is not None:
            await fixtures.CertificationLabInput.get_motor_collection().delete_one({'uuid': snapshot['uuid']})
            await fixtures.CertificationLabExecution.get_motor_collection().delete_one({'uuid': run['run_id']})
        # Synthetic prerequisites only, not claimed or awarded learner results.
        await repository.progress.update_one({'_id': ObjectId(source.progress_id)},
            {'$set': {f'modules.{module}.completed': True for module in prerequisites}})
        for name in ['runtime', 'delivery', 'practical_preparation', 'practical_execution', 'practical_assessment',
                     'practical_history', 'process_delivery', 'workflow_design_delivery', 'connected_workflow_delivery', 'advanced_workflow_delivery', 'output_workflow_delivery', 'review_delivery', 'course_history', 'scenario_history', 'upgrade_comparison']:
            module = __import__('app.services.certification_versions.' + name, fromlist=['EnrollmentRepository'])
            if hasattr(module, 'EnrollmentRepository'):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
        patches.setattr(runtime, 'versioning_enabled', lambda: True)
        config = {**fixtures.LAB_RUNTIME, 'available_models': fixtures.LAB_RUNTIME['available_models'] + fixtures.REVIEW_CONFIG['available_models'],
                  'validation_judge_model': 'synthetic-reviewer'}
        if MODULE == 'output_delivery':
            config.update(available_models=state['output_config']['available_models'] + fixtures.REVIEW_CONFIG['available_models'], default_model='report-model')
            from app.services.certification_versions import output_workflow_delivery
            patches.setattr(output_workflow_delivery, 'get_storage', lambda: storage)
        if MODULE == 'advanced_nodes':
            config.update(available_models=state['budget_config']['available_models'] + fixtures.REVIEW_CONFIG['available_models'], default_model='review-model')
            from app.services.certification_versions import advanced_workflow_delivery
            patches.setattr(advanced_workflow_delivery, 'get_storage', lambda: storage)
        patches.setattr(practical_preparation, 'configured_runtime', AsyncMock(return_value=config))
        patches.setattr(practical_preparation, 'get_storage', lambda: SimpleNamespace(read=AsyncMock(return_value=package.read('documents/' + filename))))
        if MODULE == 'multi_step':
            from app.services.certification_versions import connected_workflow_delivery
            patches.setattr(connected_workflow_delivery, 'get_storage', lambda: storage)

        def extract(*args, **kwargs):
            state['extraction_calls'] += 1
            return [entity]

        async def judge(name, settings, payload):
            state['judge_calls'] += 1
            response = await fixtures.supported_review(name, settings, payload)
            for outcome in response['outcomes']:
                outcome.update(verdict='unclear', explanation='Synthetic integration feedback; not a calibrated assessment.',
                               revision_instruction='Check each saved value against its source and record your conclusion.')
            return response

        patches.setattr(ExtractionEngine, 'extract', extract)
        patches.setattr(automatic_review, '_call_model', judge)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
        state.update(repository=repository, source=source, package=package, document=document, artifact=artifact, database=database, item_count=len(required))
        metadata = {'api_origin': 'http://127.0.0.1:5293', 'module_id': MODULE, 'database': database, 'enrollment_id': source.uuid,
                    'workflow_id': state.get('workflow_id'), 'artifact_id': artifact.uuid if artifact else None, 'document_id': document.uuid if document else None, 'run_directory': str(RUN),
                    'authentication': 'isolated fixed test actor', 'providers': 'stubbed; no live model'}
        (RUN / 'session.json').write_text(json.dumps(metadata, indent=2))
        print(json.dumps({'ready': metadata}), flush=True)
        yield
    finally:
        await client.drop_database(database)
        client.close()
        patches.undo()
        print(json.dumps({'dropped_disposable_database': database}), flush=True)

app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix='/api/certification')

@app.get('/api/extractions/search-sets')
async def extraction_choices():
    artifact = state['artifact']
    if artifact is None:
        return []
    return [{'uuid': artifact.uuid, 'title': artifact.title, 'set_type': 'extraction', 'item_count': state['item_count']}]

@app.get('/qa/state')
async def proof():
    repository, source = state['repository'], state['source']
    progress = await repository.read_progress(source.user_id, source.uuid)
    selection = await repository.selections.find_one({'user_id': source.user_id})
    return {'enrollment_id': source.uuid, 'active_enrollment_id': selection['active_enrollment_id'],
            'selection_revision': selection['revision'], 'in_flight_writes': selection['in_flight_writes'],
            'total_xp': progress.total_xp, 'certified': progress.certified,
            'extraction_calls': state['stage_providers'][0].call_count if MODULE == 'multi_step' else state['extraction_calls'], 'judge_calls': state['judge_calls'],
            **({'budget_calls': state['budget_calls']} if MODULE == 'advanced_nodes' else {}),
            **({'output_calls': state['output_calls']} if MODULE == 'output_delivery' else {}),
            **({'reasoning_calls': state['stage_providers'][1].call_count, 'formatter_calls': state['stage_providers'][2].call_count} if MODULE == 'multi_step' else {}),
            'runs': await fixtures.CertificationLabExecution.get_motor_collection().count_documents({}),
            'decisions': await fixtures.CertificationLearnerDecision.get_motor_collection().count_documents({}),
            'reviews': await fixtures.CertificationReviewAttempt.get_motor_collection().count_documents({}),
            'workflow_designs': await fixtures.CertificationWorkflowDesignSubmission.get_motor_collection().count_documents({}),
            'captures': await fixtures.CertificationLabInput.get_motor_collection().count_documents({}),
            'process_designs': await fixtures.CertificationProcessSubmission.get_motor_collection().count_documents({}),
            'credentials': await fixtures.CertificationCredential.get_motor_collection().count_documents({})}

@app.post('/qa/correct-formatter')
async def correct_formatter():
    if MODULE != 'multi_step':
        raise ValueError('This fixture has no connected Formatter')
    task = state['formatter_task']
    task.data['input_sources'] = ['step_input']
    await task.save()
    return {'formatter_input': 'step_input', 'notice': 'Synthetic fixture edit only; captured runs stay unchanged.'}

@app.post('/qa/correct-output-format')
async def correct_output_format():
    if MODULE != 'output_delivery':
        raise ValueError('This fixture has no output Formatter')
    task = state['output_formatter']
    task.data['format_template'] = 'Prepare the complete structured summary record'
    await task.save()
    return {'notice': 'Synthetic owned-workflow fixture edit only; original captures and files remain unchanged.'}

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5293, access_log=False)
