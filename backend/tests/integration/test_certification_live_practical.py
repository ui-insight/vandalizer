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
from app.models.search_set import SearchSet, SearchSetItem
from app.models.user import User
from app.services.certification_versions.catalog import CourseCatalog
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

LIVE_CONFIG = os.environ.get('CERTIFICATION_LIVE_MODEL_CONFIG')
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
