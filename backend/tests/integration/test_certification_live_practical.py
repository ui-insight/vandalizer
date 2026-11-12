"""Opt-in live practical runs: real model, real assigned source, real grader.

Unlike the full-course test, nothing here stubs the extraction model or the
automatic reviewer. A scripted synthetic learner compares the live output with
the assigned source and records what it actually finds, so a wrong extraction
must lead to revision rather than credit.

Requires a disposable CERTIFICATION_TEST_MONGO_URL plus
CERTIFICATION_LIVE_MODEL_CONFIG (a private JSON file with ``available_models``;
never commit it) and CERTIFICATION_LIVE_MODEL. Set CERTIFICATION_LIVE_REPORT to
save a per-module report. No real learner, credit claim, publication or
external message is involved.
"""
from functools import partial
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from bson import ObjectId
import fitz
import pytest

from app.models.document import SmartDocument
from app.services import workflow_engine
from app.services.extraction_engine import ExtractionEngine
from app.models.search_set import SearchSet, SearchSetItem
from app.models.user import User
from app.services.certification_versions.catalog import CourseCatalog
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

LIVE_CONFIG = os.environ.get('CERTIFICATION_LIVE_MODEL_CONFIG')
# Captured before any fixture stubs them.
REAL_PROVIDERS = {name: getattr(workflow_engine, name) for name in ('llm_chat_model', 'format_model', 'data_extraction_model')}
LIVE_CALLS = []
REAL_EXTRACT = ExtractionEngine.extract
LIVE_MODEL = os.environ.get('CERTIFICATION_LIVE_MODEL')

repo = base.repo
pytestmark = [base.pytestmark, pytest.mark.skipif(not (LIVE_CONFIG and LIVE_MODEL),
    reason='Requires CERTIFICATION_LIVE_MODEL_CONFIG and CERTIFICATION_LIVE_MODEL for an explicit live model')]

# Ground truth read from the packaged NSF sample, with the line that shows it.
FOUNDATIONS_SOURCE = {
    'PI Name': ('Dr. Sarah Chen', 'Principal Investigator: Dr. Sarah Chen'),
    'Institution': ('University of Idaho', 'Institution: University of Idaho'),
    'Total Budget': ('485000', 'Requested Amount: $485,000'),
    'Project Period': ('September 1, 2025 - August 31, 2028', 'Project Period: September 1, 2025 - August 31, 2028'),
    'Sponsoring Agency': ('National Science Foundation', 'Sponsoring Agency: National Science Foundation'),
}


# NIH repair lab: (expected value or None for absent, line that shows it).
EXTRACTION_SOURCE = {
    'Total Budget': ('1250000', 'Total Budget: $1,250,000'),
    'Postdoctoral Fellow Name': (None, 'TBD'),
    'Human Subjects': ('No', 'Human Subjects: No'),
    'Vertebrate Animals': ('Yes', 'Vertebrate Animals: Yes - Mouse model (Mus musculus)'),
}


def live_runtime():
    config = json.loads(Path(LIVE_CONFIG).read_text())
    if sum(model.get('name') == LIVE_MODEL for model in config.get('available_models', [])) != 1:
        raise AssertionError('The live config must name the selected model exactly once')
    return {'available_models': config['available_models'],
            'extraction_config': {'mode': 'one_pass', 'model': LIVE_MODEL}}


def normalized(value):
    text = str(value or '').casefold()
    text = re.sub(r'^(dr\.?|prof\.?)\s+', '', text.strip())
    digits = re.sub(r'[^0-9]', '', text)
    if digits and re.fullmatch(r'[\s$usd,.0-9]+', text):
        return digits
    return re.sub(r'[\s,.]+', ' ', text.replace('–', '-').replace('—', '-')).strip()


def record(module_id, entry):
    path = os.environ.get('CERTIFICATION_LIVE_REPORT')
    if not path:
        return
    report = json.loads(Path(path).read_text()) if Path(path).exists() else {'model': LIVE_MODEL, 'modules': {}}
    report['modules'][module_id] = entry
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True))


def route_workflow_models_live(monkeypatch, runtime_config):
    """Send every workflow model call to the live model, whatever fixture name a task saved.

    Saved plans keep the fixture's model labels; the calls themselves are live.
    """
    def routed(name):
        real = REAL_PROVIDERS[name]

        def call(model, *args, **kwargs):
            kwargs['system_config_doc'] = runtime_config
            result = real(LIVE_MODEL, *args, **kwargs)
            LIVE_CALLS.append((name, model, str(result)[:200]))
            return result
        return call
    for name in REAL_PROVIDERS:
        monkeypatch.setattr(workflow_engine, name, routed(name))


def after_fixture(monkeypatch, module, runtime_config):
    """Re-apply live routing after a shared fixture installs its provider stubs."""
    original = module.fixture

    async def wrapped(*args, **kwargs):
        built = await original(*args, **kwargs)
        route_workflow_models_live(monkeypatch, runtime_config)
        return built
    monkeypatch.setattr(module, 'fixture', wrapped)


async def prepare_live_review(repo, learner, package, run_id, runtime_config):
    from app.services.certification_versions.review_attempts import ReviewAttemptRepository
    from app.services.certification_versions.runtime import CourseOperation
    async with repo.write_boundary(learner.user_id, learner.uuid, operation='prepare_trusted_review') as progress:
        return await ReviewAttemptRepository().prepare_from_run(CourseOperation(learner.user_id, package, progress, True),
            run_id, uuid4().hex, actor_user_id=learner.user_id, model_name=LIVE_MODEL, system_config=runtime_config)


async def enrolled_learner(repo, tmp_path, monkeypatch):
    from app.services.certification_versions import module_readiness, runtime
    authored = candidate.__wrapped__(tmp_path)
    path = authored.folder.parent / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    path.write_text(json.dumps(registry))
    repo.catalog = CourseCatalog(authored.folder.parent)
    await User(user_id='live-practical-learner', name='Synthetic Live QA Learner', email='live-qa@example.test').insert()
    learner = await repo.ensure_initial('live-practical-learner')
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    return learner, repo.catalog.load(VERSION)


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_foundations_live_extraction_is_checked_by_the_learner_and_graded_by_the_live_reviewer(repo, tmp_path, monkeypatch, behavior):
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    data = package.read('documents/nsf-proposal-alpine-ecology.pdf')
    with fitz.open(stream=data, filetype='pdf') as pdf:
        source_text = '\n\n'.join(page.get_text() for page in pdf)
    assert all(quote in source_text for _, quote in FOUNDATIONS_SOURCE.values())
    document = await SmartDocument(uuid=uuid4().hex, user_id=learner.user_id,
        title='nsf-proposal-alpine-ecology.pdf', path='synthetic/foundation.pdf',
        downloadpath='synthetic/foundation.pdf', raw_text=source_text,
        folder='live-foundations', processing=False, task_status='completed').insert()
    artifact = await SearchSet(uuid=uuid4().hex, user_id=learner.user_id,
        title='Five source-bound fields', status='active', set_type='extraction').insert()
    for title in FOUNDATIONS_SOURCE:
        await SearchSetItem(searchset=artifact.uuid, user_id=learner.user_id,
            title=title, searchphrase=title, searchtype='extraction').insert()
    await repo.progress.update_one({'_id': ObjectId(learner.progress_id)}, {'$set': {
        'lab_folder_id': document.folder, 'modules.foundations.provisioned_docs': [document.uuid]}})
    snapshot = await base.capture_lab(repo, learner, package, artifact.uuid,
        SimpleNamespace(read=AsyncMock(return_value=data)))

    run = await base.execute_lab(repo, learner, package, snapshot['uuid'], uuid4().hex,
                                 config=runtime_config, prepare_only=True)
    await base.submit_learner_decision(repo, learner, package,
        base.scope_proposal_submission(package, run, document.uuid))
    run = await base.execute_lab(repo, learner, package, snapshot['uuid'], run['run_id'], config=runtime_config)
    assert run['state'] == 'completed', run.get('result')
    output = run['result']['entities'][0]

    # The synthetic learner records what it actually finds, never the expected answer.
    checks, matched = [], {}
    for field, (truth, quote) in FOUNDATIONS_SOURCE.items():
        produced = str(output.get(field) or '')
        matched[field] = normalized(produced) == normalized(truth)
        checks.append({'field': field, 'decision': 'supported' if matched[field] else 'unsupported',
            'checked_value': produced, 'source_document_id': document.uuid, 'source_quote': quote,
            'reason': ('The output matches the quoted line of the assigned source.' if matched[field] else
                       f'The assigned source says "{quote}", which the output does not match.')})
    if behavior == 'careless':
        # Accepts a budget that contradicts the very line it quotes.
        budget = next(check for check in checks if check['field'] == 'Total Budget')
        budget.update(decision='supported', checked_value='$458,000',
                      reason='I looked at the budget line and the amount is correct.')
    body = base.learner_decision_submission(package, run['run_id'], 'value_review', document=document)
    honest = behavior == 'honest' and all(matched.values())
    body.update(choice='accept' if honest or behavior == 'careless' else 'repair', value_checks=checks)
    await base.submit_learner_decision(repo, learner, package, body, 'value_review')

    prepared = await prepare_live_review(repo, learner, package, run['run_id'], runtime_config)
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(f'foundations-{behavior}', {'run_state': run['state'], 'output': output, 'field_matches': matched,
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'deterministic': assessment.get('deterministic_outcomes'), 'credit_awarded': assessment['credit_awarded']})

    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False
    if behavior == 'careless':
        assert assessment['status'] == 'revision_required', assessment
        assert assessment['passed'] is False
    elif all(matched.values()):
        assert assessment['status'] == 'requirements_supported', assessment
    else:
        assert assessment['status'] == 'revision_required', assessment


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_extraction_repair_live_run_is_checked_by_the_learner_and_graded_by_the_live_reviewer(repo, tmp_path, monkeypatch, behavior):
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    # Every shared lab helper now prepares and executes against the live model.
    monkeypatch.setattr(base, 'LAB_RUNTIME', runtime_config)
    _, _, document, _, snapshot, run = await base.extraction_repair_fixture(repo, enrolled=(learner, package))
    assert all(quote in document.raw_text for _, quote in EXTRACTION_SOURCE.values())
    await base.submit_repair_decision(repo, learner, package, base.repair_decision_submission(package, run))
    run = await base.execute_lab(repo, learner, package, snapshot['uuid'], run['run_id'])
    assert run['state'] == 'completed', run.get('result')
    phrase = {field['title']: field['searchphrase'] for field in snapshot['artifact']['fields']}
    output = run['result']['entities'][0]

    checks, matched = [], {}
    for field, (truth, quote) in EXTRACTION_SOURCE.items():
        produced = output.get(phrase[field])
        absent = produced in (None, '') or normalized(produced) in ('none', 'null', 'tbd', 'n/a')
        matched[field] = absent if truth is None else normalized(produced) == normalized(truth)
        checks.append({'field': field, 'decision': 'supported' if matched[field] else 'unsupported',
            'checked_value': '' if produced is None else str(produced), 'source_document_id': document.uuid,
            'source_quote': quote,
            'reason': ('The output matches the quoted line of the assigned source.' if matched[field] and truth is not None else
                       'The source lists only TBD, so the value is correctly left absent.' if matched[field] else
                       f'The assigned source says "{quote}", which the output does not match.')})
    if behavior == 'careless':
        # Falls for the annual-allocation trap the repair case is built around.
        budget = next(check for check in checks if check['field'] == 'Total Budget')
        budget.update(decision='supported', checked_value='304000',
                      reason='The budget table shows the amount, so the total is correct.')
    body = base.repair_decision_submission(package, run, 'repair_values', document)
    honest = behavior == 'honest' and all(matched.values())
    body.update(choice='accept' if honest or behavior == 'careless' else 'repair', value_checks=checks,
                reason='I compared each repaired value with the assigned NIH source before deciding.')
    await base.submit_repair_decision(repo, learner, package, body, 'repair_values')

    prepared = await prepare_live_review(repo, learner, package, run['run_id'], runtime_config)
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(f'extraction_engine-{behavior}', {'run_state': run['state'],
        'output': {field: output.get(phrase[field]) for field in EXTRACTION_SOURCE}, 'field_matches': matched,
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})

    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False
    if behavior == 'careless' or not all(matched.values()):
        assert assessment['status'] == 'revision_required', assessment
    else:
        assert assessment['status'] == 'requirements_supported', assessment


@pytest.mark.parametrize('module_id', ['process_mapping', 'workflow_design'])
async def test_thin_design_answers_are_sent_back_by_the_live_reviewer(repo, tmp_path, monkeypatch, module_id):
    # The shared fixture answers name the right choices without explaining
    # them. A nonempty explanation alone must not earn the outcome.
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)
    for name in ('process_design_fixture', 'connected_workflow_fixture'):
        monkeypatch.setattr(base, name, partial(getattr(base, name), enrolled=(learner, package)))
    if module_id == 'process_mapping':
        _, _, _, body = await base.process_design_fixture(repo)
        saved = await base.save_process(repo, learner, package, body)
        prepared = await base.prepare_process_review(repo, learner, package, saved['uuid'])
    else:
        _, _, _, body = await base.workflow_approval_fixture(repo)
        saved = await base.approve_workflow_design(repo, learner, package, body)
        prepared = await base.prepare_workflow_review(repo, learner, package, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(module_id, {'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})
    assert assessment['status'] == 'revision_required', assessment
    assert assessment['credit_awarded'] is False
    unmet = [item for item in assessment['outcomes'] if item['verdict'] != 'supported']
    assert unmet and all(len(item['revision_instruction']) >= 10 for item in unmet)


async def run_connected_revision(repo, fixture, runtime_config):
    from app.services.certification_versions.connected_workflow_execution import ConnectedWorkflowExecution
    from app.services.certification_versions.connected_workflow_preparation import ConnectedWorkflowPreparation
    from app.services.certification_versions.runtime import CourseOperation
    learner, package = fixture[:2]
    capture_body = fixture[7]
    capture_body['request_id'] = uuid4().hex
    snapshot = await base.capture_connected(repo, fixture)
    async with repo.write_boundary(learner.user_id, learner.uuid, operation='prepare_connected_workflow') as progress:
        planned = await ConnectedWorkflowPreparation().prepare(CourseOperation(learner.user_id, package, progress, True),
            base.connected_plan_body(snapshot), runtime_config, actor_user_id=learner.user_id, default_model=LIVE_MODEL)
    await base.submit_connected_scope(repo, fixture, base.connected_scope_body(planned))
    approved = await ConnectedWorkflowExecution().get(learner.user_id, planned['run_id'])
    return await base.dispatch_connected(repo, fixture, base.connected_execution_body(approved), config=runtime_config)


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_multi_step_live_runs_compare_a_broken_and_repaired_connection(repo, tmp_path, monkeypatch, behavior):
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)
    monkeypatch.setattr(base, 'connected_workflow_fixture', partial(base.connected_workflow_fixture, enrolled=(learner, package)))
    fixture = await base.connected_workflow_fixture(repo)
    tasks = fixture[5]
    # The authored flaw: the Formatter rereads the source instead of the reasoning result.
    tasks[2].data['input_sources'] = ['workflow_documents']
    await tasks[2].save()
    original = await run_connected_revision(repo, fixture, runtime_config)
    if behavior == 'honest':
        tasks[2].data['input_sources'] = ['step_input']
        await tasks[2].save()
    # A careless learner reruns without repairing the connection.
    corrected = await run_connected_revision(repo, fixture, runtime_config)
    assert original['state'] == corrected['state'] == 'completed', (original.get('result'), corrected.get('result'))

    try:
        saved = await base.submit_connected_review(repo, fixture, base.connected_review_body(original, corrected))
    except Exception as refused:
        assert behavior == 'careless', refused
        record('multi_step-careless', {'refused_at': 'submit_connected_review', 'reason': str(refused)[:300]})
        return
    prepared = await base.prepare_connected_assessment(repo, fixture, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(f'multi_step-{behavior}', {'states': [original['state'], corrected['state']],
        'final_outputs': [str(run['result'].get('final_output'))[:600] for run in (original, corrected)],
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'deterministic': [(item['outcome_id'], item['passed']) for item in assessment.get('deterministic_outcomes', [])],
        'credit_awarded': assessment['credit_awarded']})
    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False
    connected = next(item for item in assessment['deterministic_outcomes'] if item['outcome_id'] == 'multi_step.connected_execution')
    if behavior == 'careless':
        assert assessment['status'] == 'revision_required' and assessment['passed'] is False, assessment
    else:
        assert connected['passed'] is True
        assert assessment['status'] == 'requirements_supported', assessment


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_advanced_nodes_live_parallel_reviews_and_memo(repo, tmp_path, monkeypatch, behavior):
    from tests.integration import test_certification_advanced_calculation_records as budget_inputs
    from tests.integration import test_certification_advanced_workflow_execution as budget_execution
    from tests.integration import test_certification_advanced_workflow_reviews as budget
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    LIVE_CALLS.clear()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)
    monkeypatch.setattr(budget_inputs, 'fixture', partial(budget_inputs.fixture, enrolled=(learner, package)))
    after_fixture(monkeypatch, budget_execution, runtime_config)
    # The careless learner keeps a wrong equipment sum (45001.00 for 45000.00).
    f = await budget.fixture(repo, monkeypatch, correct=behavior == 'honest')
    saved = await budget.submit(repo, f)
    prepared = await budget.prepare(repo, f, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(f'advanced_nodes-{behavior}', {'run_state': f.completed['state'],
        'live_calls': list(LIVE_CALLS),
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'deterministic': [(item['outcome_id'], item['passed']) for item in assessment.get('deterministic_outcomes', [])],
        'credit_awarded': assessment['credit_awarded']})
    assert f.completed['state'] == 'completed'
    # Two parallel reviews and the memo, each answered by the live model.
    assert len(LIVE_CALLS) == 3 and not any(output.startswith('RESULT: ') for _, _, output in LIVE_CALLS)
    assert assessment['credit_awarded'] is False
    if behavior == 'careless':
        assert assessment['status'] == 'revision_required', assessment
        verdicts = {item['outcome_id']: item['verdict'] for item in assessment['outcomes']}
        assert verdicts['advanced_nodes.checked_computation'] != 'supported'
    else:
        assert assessment['status'] == 'requirements_supported', assessment


def competent_output_prompts(monkeypatch):
    """Replace the fixture's placeholder instructions with ones a competent learner writes."""
    from app.services.certification_versions.output_case import REQUIRED_FIELDS
    from tests.integration import test_certification_output_workflow_plan as output_plan
    fields = ', '.join(f'"{name}"' for name in REQUIRED_FIELDS)
    instruction = ('From the assigned progress report only, return one JSON object with exactly these keys: '
                   f'{fields}. Copy values as stated in the report, keep currency amounts as written, '
                   'write "Not stated" when the report does not give a value, and list the pages used in '
                   '"Source References". Return only the JSON object.')
    original = output_plan.fixture

    async def fixture(repo, **kwargs):
        f = await original(repo, **kwargs)
        f.tasks[0].data['prompt'] = instruction
        f.tasks[2].data['format_template'] = instruction
        for task in (f.tasks[0], f.tasks[2]):
            await task.save()
        f.body['request_id'] = uuid4().hex
        f.saved = await output_plan.capture_fixtures.capture(repo, f)
        return f
    monkeypatch.setattr(output_plan, 'fixture', fixture)


@pytest.mark.parametrize('behavior', ['competent', 'vague'])
async def test_output_delivery_live_generation_review_and_private_handoff(repo, tmp_path, monkeypatch, behavior):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from tests.integration import test_certification_output_workflow_inputs as output_inputs
    from tests.integration import test_certification_output_workflow_execution as output_execution
    from tests.integration import test_certification_output_outcome_reviews as output
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    LIVE_CALLS.clear()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)
    monkeypatch.setattr(output_inputs, 'fixture', partial(output_inputs.fixture, enrolled=(learner, package)))
    after_fixture(monkeypatch, output_execution, runtime_config)
    if behavior == 'competent':
        competent_output_prompts(monkeypatch)
    else:
        # Placeholder instructions yield prose, so the generated files fail
        # validation and release approval must be refused.
        with pytest.raises(EnrollmentConflict, match='invalid or incomplete generated files'):
            await output.fixture(repo, monkeypatch)
        record('output_delivery-vague', {'live_calls': [(n, m, o[:200]) for n, m, o in LIVE_CALLS],
                                         'refused': 'release approval of unparseable generated files'})
        assert LIVE_CALLS
        return
    f = await output.fixture(repo, monkeypatch)
    saved = await output.submit(repo, f)
    prepared = await output.prepare(repo, f, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record('output_delivery-competent', {'live_calls': [(n, m, o[:300]) for n, m, o in LIVE_CALLS],
        'handoff_status': f.handoff.get('status'), 'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})
    assert LIVE_CALLS
    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False


async def test_batch_live_extraction_controlled_failure_and_targeted_retry(repo, tmp_path, monkeypatch):
    from tests.integration import test_certification_batch_inputs as batch_inputs
    from tests.integration import test_certification_batch_execution as batch_execution
    from tests.integration import test_certification_batch_reviews as batch
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    LIVE_CALLS.clear()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)
    monkeypatch.setattr(batch_inputs, 'fixture', partial(batch_inputs.fixture, enrolled=(learner, package)))

    def live_provider(f, wrong=False):
        def extract(**kwargs):
            # Run the real engine on exactly the inputs the batch dispatched.
            kwargs.update(model=LIVE_MODEL, extraction_config_override={'mode': 'one_pass', 'model': LIVE_MODEL})
            result = REAL_EXTRACT(ExtractionEngine(system_config_doc=runtime_config), **kwargs)
            LIVE_CALLS.append(('extract', LIVE_MODEL, json.dumps(result, default=str)[:300]))
            return result
        return extract
    monkeypatch.setattr(batch_execution, 'provider', live_provider)

    f = await batch.fixture(repo)
    saved = await batch.submit(repo, f)
    prepared = await batch.prepare(repo, f, saved['uuid'])
    assessment, technical_retries, unavailable = await evaluate_with_technical_retry(
        repo, learner, package, prepared['attempt_id'], runtime_config)
    record('batch_processing', {'live_calls': list(LIVE_CALLS), 'technical_retries': technical_retries,
        'unavailable_reasons': unavailable,
        'states': [f.original['state'], f.retry['state']], 'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'deterministic': [(item['outcome_id'], item['passed']) for item in assessment.get('deterministic_outcomes', [])],
        'credit_awarded': assessment['credit_awarded']})
    assert LIVE_CALLS
    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False


async def evaluate_with_technical_retry(repo, learner, package, attempt_id, runtime_config):
    """Grade once; on a technical gap, take the learner's explicit retry once.

    The product never retries on its own, so the test asks the way a learner
    would. Returns the assessment, the number of retries and any unavailable reasons.
    """
    reviewed = await base.evaluate_review(repo, learner, package, attempt_id, config=runtime_config)
    assessment = reviewed['result']['assessment']
    reasons = []
    if assessment['status'] == 'grading_unavailable':
        reasons.append(assessment.get('reason'))
        child = await base.retry_review(repo, learner, package, attempt_id, config=runtime_config)
        reviewed = await base.evaluate_review(repo, learner, package, child['attempt_id'], config=runtime_config)
        assessment = reviewed['result']['assessment']
        return assessment, 1, reasons
    return assessment, 0, reasons


def live_after_controlled_failure(scripted, runtime_config):
    """Keep the scripted original failure; run every repaired extraction live."""
    def provider(f, *, wrong=False):
        if wrong:
            return scripted(f, wrong=True)

        def extract(**kwargs):
            kwargs.update(model=LIVE_MODEL, extraction_config_override={'mode': 'one_pass', 'model': LIVE_MODEL})
            result = REAL_EXTRACT(ExtractionEngine(system_config_doc=runtime_config), **kwargs)
            LIVE_CALLS.append(('extract', LIVE_MODEL, json.dumps(result, default=str)[:300]))
            return result
        return extract
    return provider


def live_reviewer(monkeypatch, runtime_config):
    LIVE_CALLS.clear()
    monkeypatch.setattr(base, 'REVIEW_CONFIG', runtime_config)
    monkeypatch.setattr(base, 'REVIEW_MODEL', LIVE_MODEL)


CARELESS_VALIDATION = 'I fixed the budget prompt and reran it. Everything is correct now, so the extraction will work on any proposal.'
CARELESS_SUPERVISION = 'I fixed the funding prompt, reran it and sent the memo. The workflow is reliable now and ready for real awards.'


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_validation_live_retest_after_repair_is_graded_by_the_live_reviewer(repo, tmp_path, monkeypatch, behavior):
    from tests.integration import test_certification_validation_execution as execution
    from tests.integration import test_certification_validation_inputs as inputs
    from tests.integration import test_certification_validation_reviews as validation
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    live_reviewer(monkeypatch, runtime_config)
    monkeypatch.setattr(inputs, 'fixture', partial(inputs.fixture, enrolled=(learner, package)))
    monkeypatch.setattr(execution, 'provider', live_after_controlled_failure(execution.provider, runtime_config))

    f = await validation.fixture(repo)
    checks = f.corrected['result']['checks']
    if behavior == 'careless':
        f.review_body['answers']['repair_review'] = CARELESS_VALIDATION
    saved = await validation.submit(repo, f)
    prepared = await validation.prepare(repo, f, saved['uuid'])
    assessment, technical_retries, unavailable = await evaluate_with_technical_retry(
        repo, learner, package, prepared['attempt_id'], runtime_config)
    record(f'validation_qa-{behavior}', {'live_calls': list(LIVE_CALLS), 'retest_checks': checks,
        'technical_retries': technical_retries, 'unavailable_reasons': unavailable,
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})

    assert LIVE_CALLS
    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False
    if behavior == 'careless' or not checks['source_supported']:
        assert assessment['status'] == 'revision_required', assessment
    else:
        assert assessment['status'] == 'requirements_supported', assessment


@pytest.mark.parametrize('behavior', ['honest', 'careless'])
async def test_governance_live_capstone_rerun_and_supervision_graded_by_the_live_reviewer(repo, tmp_path, monkeypatch, behavior):
    from tests.integration import test_certification_governance_execution as execution
    from tests.integration import test_certification_governance_inputs as inputs
    from tests.integration import test_certification_governance_reviews as governance
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    live_reviewer(monkeypatch, runtime_config)
    monkeypatch.setattr(inputs, 'fixture', partial(inputs.fixture, enrolled=(learner, package)))
    monkeypatch.setattr(execution, 'provider', live_after_controlled_failure(execution.provider, runtime_config))
    runs, execute = [], execution.execute

    async def recorded_execute(*args, **kwargs):
        runs.append(await execute(*args, **kwargs))
        return runs[-1]
    monkeypatch.setattr(execution, 'execute', recorded_execute)

    try:
        f = await governance.fixture(repo)
    except Exception as error:
        final = runs[-1]['result']['checks']
        record(f'governance-{behavior}', {'live_calls': list(LIVE_CALLS), 'final_checks': final,
            'refused_before_review': repr(error)})
        # The product refuses a memo over a rerun that is not source-correct;
        # an honest learner stops there. Anything else is a real failure.
        if final['source_supported']:
            raise
        return
    checks = f.final['result']['checks']
    if behavior == 'careless':
        f.review_body['final_supervision'] = CARELESS_SUPERVISION
    saved = await governance.submit(repo, f)
    prepared = await governance.prepare(repo, f, saved['uuid'])
    assessment, technical_retries, unavailable = await evaluate_with_technical_retry(
        repo, learner, package, prepared['attempt_id'], runtime_config)
    record(f'governance-{behavior}', {'live_calls': list(LIVE_CALLS), 'final_checks': checks,
        'technical_retries': technical_retries, 'unavailable_reasons': unavailable,
        'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})

    assert LIVE_CALLS
    assert assessment['status'] != 'grading_unavailable', assessment.get('reason')
    assert assessment['credit_awarded'] is False
    if behavior == 'careless' or not checks['source_supported']:
        assert assessment['status'] == 'revision_required', assessment
    else:
        assert assessment['status'] == 'requirements_supported', assessment


STRONG_METHOD_CHOICE = ('I choose a bounded workflow. The three monthly reports share a similar form for milestones and spending, '
    'but the narrative varies, so a reusable extraction alone would drop the context needed to interpret milestones and '
    'conflicting passages. The review repeats every month, so a one-off chat question would be re-asked and re-checked each '
    'time. The required output is an internal comparison draft of milestones, spending and unresolved issues with source '
    'references, which needs organizing, comparing and formatting stages. Institutional judgment stays with the grants '
    'reviewer, so the workflow ends at the draft. A one-off question would use chat; a repeated fixed-field intake without '
    'narrative would need only a reusable extraction.')
STRONG_PROCESS_MAP = ('1. Input (reviewer, then agent): the grants reviewer names report-alpine, report-neural and report-water; '
    'the agent confirms each is readable and flags a missing or unreadable passage by page. 2. Repetitive preparation (agent): '
    'extract milestones, reported spending, approved monthly budget and incomplete activities from each report, each value with '
    'its source passage. 3. Deterministic calculation (code): spending variance = reported spending minus approved monthly budget, '
    'showing both inputs and the result; the model does not estimate it. 4. Institutional judgment (grants reviewer): whether an '
    'overspend is justified. The suggested map gave this to the agent and let it mark overspends resolved; I moved it to the '
    'reviewer and the agent closes nothing. 5. Handoff (agent to reviewer): the internal draft comparison with every source and '
    'intermediate reference, conflicting passages quoted side by side and missing passages flagged. 6. Output (grants reviewer): '
    'the reviewer inspects the references, variances and flagged items and records a decision; unresolved items return for '
    'correction and nothing is sent or released. From the flawed proposal I also removed the search of every project file, the '
    'agent approval, the automatic external email with review afterward and the guessed milestones.')
STRONG_PROMPT = ('Using only the workflow documents (report-alpine, report-neural and report-water), compare the reported '
    'milestones and spending. Cite the document and passage for every value. List unresolved issues separately. If a '
    'required passage is missing or unreadable, or two passages conflict, do not guess or treat it as zero or agreement: '
    'mark the affected conclusion BLOCKED, quote the passages involved and leave it for the grants reviewer. Produce an '
    'internal draft only; do not approve, send, share or schedule anything.')
# The same instruction in other words: wording must not be an accidental requirement.
PARAPHRASED_PROMPT = ('Read report-alpine, report-neural and report-water, the workflow documents and nothing else. Build an '
    'internal side-by-side of each project\'s milestones and spending, and give the report and passage behind every figure. '
    'Keep open issues in their own list. When a passage the comparison needs is absent or illegible, or two passages '
    'disagree, flag that item UNRESOLVED, quote what you found and hand it to the grants reviewer instead of estimating, '
    'counting it as zero or picking one. This is a draft for internal review: send, share, schedule and approve nothing.')
STRONG_WORKFLOW_ANSWERS = {
    'data_flow': 'I chose my original saved process submission. The one saved Prompt step takes the workflow documents as its '
        'input, which at run time are only report-alpine, report-neural and report-water, and compares them directly: a prompt '
        'over short relevant source text keeps the narrative context a separate extraction would drop. Its output, the internal '
        'comparison draft, is the only output step; it uses no prior saved text. Trace: report-alpine\'s reported spending is '
        'read from that report, appears in its comparison row with a document and passage reference, and reaches the draft '
        'unchanged; if report-water\'s passages disagree about an activity, both are quoted with references as an unresolved '
        'issue. This is a saved design, not an executed run.',
    'approval_boundary': 'The flawed proposal sent the report to an unapproved external partner and added approval afterward '
        'with automatic approval on timeout. I removed the external destination and the after-the-fact approval; the saved '
        'revision ends at the internal draft with no send, share or schedule. I approve this saved design for assessment only; '
        'execution or release needs a separate decision.',
    'reviewable_design': 'The saved prompt keeps a document and passage reference for every milestone and spending value and '
        'lists unresolved issues separately. If a required report-neural passage is missing or unreadable, or report-water\'s '
        'passages conflict, the prompt marks the affected conclusion BLOCKED and quotes the passages instead of guessing or '
        'treating it as zero, and the draft still goes only to the reviewer. The fictional grants reviewer inspects those '
        'references and blocked items before any conclusion; nothing is released. This is the design\'s intended behavior; I '
        'have not executed it.'}


@pytest.mark.parametrize('module_id', ['process_mapping', 'workflow_design', 'workflow_design_paraphrased'])
async def test_strong_design_answers_are_accepted_by_the_live_reviewer(repo, tmp_path, monkeypatch, module_id):
    # The counterpart to the thin-answer test: the same saved case, explained
    # against each passing condition, must not be sent back.
    from app.services.certification_versions.attempts import encode
    learner, package = await enrolled_learner(repo, tmp_path, monkeypatch)
    runtime_config = live_runtime()
    live_reviewer(monkeypatch, runtime_config)
    for name in ('process_design_fixture', 'connected_workflow_fixture'):
        monkeypatch.setattr(base, name, partial(getattr(base, name), enrolled=(learner, package)))
    if module_id == 'process_mapping':
        _, _, _, body = await base.process_design_fixture(repo)
        body['answers']['method_choice'] = STRONG_METHOD_CHOICE
        body['answers']['human_checkpoint'] = STRONG_PROCESS_MAP
        saved = await base.save_process(repo, learner, package, body)
        prepared = await base.prepare_process_review(repo, learner, package, saved['uuid'])
    else:
        _, _, _, _, _, task, capture_body = await base.workflow_design_capture_fixture(repo)
        paraphrased = module_id == 'workflow_design_paraphrased'
        task.data = {**task.data, 'prompt': PARAPHRASED_PROMPT if paraphrased else STRONG_PROMPT}
        await task.save()
        snapshot = await base.capture_workflow_design(repo, learner, package, capture_body)
        answers = ({key: value.replace('BLOCKED', 'UNRESOLVED') for key, value in STRONG_WORKFLOW_ANSWERS.items()}
                   if paraphrased else STRONG_WORKFLOW_ANSWERS)
        body = {'request_id': uuid4().hex, 'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': encode(snapshot)[1],
            'case_sha256': snapshot['case']['case_sha256'], 'consent': 'approve_saved_workflow_design_for_assessment',
            'answers': answers}
        saved = await base.approve_workflow_design(repo, learner, package, body)
        prepared = await base.prepare_workflow_review(repo, learner, package, saved['uuid'])
    reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], config=runtime_config)
    assessment = reviewed['result']['assessment']
    record(f'{module_id}-strong', {'assessment_status': assessment['status'],
        'verdicts': {item['outcome_id']: item['verdict'] for item in assessment.get('outcomes', [])},
        'explanations': {item['outcome_id']: item['explanation'] for item in assessment.get('outcomes', [])},
        'credit_awarded': assessment['credit_awarded']})
    assert assessment['status'] == 'requirements_supported', assessment
    assert assessment['credit_awarded'] is False
