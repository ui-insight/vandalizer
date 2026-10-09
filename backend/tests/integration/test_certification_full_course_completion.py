"""One immutable eleven-module course, real saved evidence, stubbed providers.

Synthetic release metadata is not live-model calibration or release acceptance.
No receipt is transplanted from another enrollment or rewritten after creation.
"""
from functools import partial
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
import fitz
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.models.certification import (
    CertificationAttempt, CertificationLabInput, CertificationLabExecution,
    CertificationLearnerDecision, CertificationProcessSubmission,
    CertificationWorkflowDesignSubmission,
)
from app.models.document import SmartDocument
from app.models.search_set import SearchSet, SearchSetItem
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from app.routers.certification import router
from app.services.certification_versions import module_readiness, runtime
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.outcome_credit import verified_credit_snapshot
from app.services.certification_versions.outcomes import package_outcomes
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.review_attempts import ReviewAttemptRepository
from app.services.certification_versions.review_delivery import ReviewDelivery
from app.services.certification_versions.scenario_submissions import module_bank, ScenarioSubmissionRepository
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_advanced_calculation_records as budget_inputs
from tests.integration import test_certification_advanced_workflow_reviews as budget
from tests.integration import test_certification_output_workflow_inputs as output_inputs
from tests.integration import test_certification_output_outcome_reviews as output
from tests.integration import test_certification_batch_inputs as batch_inputs
from tests.integration import test_certification_batch_reviews as batch
from tests.integration import test_certification_validation_inputs as validation_inputs
from tests.integration import test_certification_validation_reviews as validation
from tests.integration import test_certification_governance_inputs as governance_inputs
from tests.integration import test_certification_governance_reviews as governance
from tests.test_certification_outcome_rubric import candidate, VERSION

repo = base.repo
pytestmark = base.pytestmark


async def foundation_review(repo, learner, package):
    """Capture five real source checks against the assembled Foundation exercise."""
    data = package.read('documents/nsf-proposal-alpine-ecology.pdf')
    with fitz.open(stream=data, filetype='pdf') as pdf:
        source_text = '\n\n'.join(page.get_text() for page in pdf)
    document = await SmartDocument(uuid=uuid4().hex, user_id=learner.user_id,
        title='nsf-proposal-alpine-ecology.pdf', path='synthetic/foundation.pdf',
        downloadpath='synthetic/foundation.pdf', raw_text=source_text,
        folder='full-course-foundations', processing=False, task_status='completed').insert()
    artifact = await SearchSet(uuid=uuid4().hex, user_id=learner.user_id,
        title='Five source-bound fields', status='active', set_type='extraction').insert()
    values = {
        'PI Name': ('Dr. Sarah Chen', 'Principal Investigator: Dr. Sarah Chen'),
        'Institution': ('University of Idaho', 'Institution: University of Idaho'),
        'Total Budget': ('485000', 'Requested Amount: $485,000'),
        'Project Period': ('September 1, 2025 - August 31, 2028', 'Project Period: September 1, 2025 - August 31, 2028'),
        'Sponsoring Agency': ('National Science Foundation', 'Sponsoring Agency: National Science Foundation'),
    }
    for title in values:
        await SearchSetItem(searchset=artifact.uuid, user_id=learner.user_id,
            title=title, searchphrase=title, searchtype='extraction').insert()
    await repo.progress.update_one({'_id': ObjectId(learner.progress_id)}, {'$set': {
        'lab_folder_id': document.folder, 'modules.foundations.provisioned_docs': [document.uuid]}})
    snapshot = await base.capture_lab(repo, learner, package, artifact.uuid,
        SimpleNamespace(read=AsyncMock(return_value=data)))
    run = await base.execute_lab(repo, learner, package, snapshot['uuid'], uuid4().hex, prepare_only=True)
    await base.submit_learner_decision(repo, learner, package,
        base.scope_proposal_submission(package, run, document.uuid))
    with patch('app.services.extraction_engine.ExtractionEngine.extract',
               return_value=[{name: item[0] for name, item in values.items()}]):
        run = await base.execute_lab(repo, learner, package, snapshot['uuid'], run['run_id'])
    body = base.learner_decision_submission(package, run['run_id'], 'value_review', document=document)
    body.update(choice='accept', value_checks=[{
        'field': name, 'decision': 'supported', 'checked_value': value,
        'source_document_id': document.uuid, 'source_quote': quote,
        'reason': 'I checked the named field against the saved assigned source.'
    } for name, (value, quote) in values.items()])
    await base.submit_learner_decision(repo, learner, package, body, 'value_review')
    return await base.prepare_trusted_review(repo, learner, package, run['run_id'])


async def review_for(module_id, repo, learner, package, monkeypatch):
    if module_id == 'ai_literacy':
        return None
    if module_id == 'foundations':
        return await foundation_review(repo, learner, package)
    if module_id == 'extraction_engine':
        _, _, _, _, run, _ = await base.completed_repair_fixture(repo)
        return await base.prepare_trusted_review(repo, learner, package, run['run_id'])
    if module_id == 'process_mapping':
        _, _, _, body = await base.process_design_fixture(repo)
        saved = await base.save_process(repo, learner, package, body)
        return await base.prepare_process_review(repo, learner, package, saved['uuid'])
    if module_id == 'workflow_design':
        _, _, _, body = await base.workflow_approval_fixture(repo)
        saved = await base.approve_workflow_design(repo, learner, package, body)
        return await base.prepare_workflow_review(repo, learner, package, saved['uuid'])
    if module_id == 'multi_step':
        fixture, original, corrected, _ = await base.connected_pair_fixture(repo, monkeypatch)
        saved = await base.submit_connected_review(repo, fixture, base.connected_review_body(original, corrected))
        return await base.prepare_connected_assessment(repo, fixture, saved['uuid'])
    service = {'advanced_nodes': budget, 'output_delivery': output, 'batch_processing': batch,
               'validation_qa': validation, 'governance': governance}[module_id]
    if service is budget:
        fixture = await service.fixture(repo, monkeypatch, correct=True)
    elif service is output:
        fixture = await service.fixture(repo, monkeypatch)
    else:
        fixture = await service.fixture(repo)
    saved = await service.submit(repo, fixture)
    return await service.prepare(repo, fixture, saved['uuid'])


async def preserve_awarded_evidence_after_workspace_deletion(repo, learner, package, earned):
    """Delete only fixture data in this test's disposable database.

    Keep the assessment journals: those are the durable evidence behind credit,
    separate from editable workspace records and intermediate lab records.
    """
    repositories = {'automatic_review': ReviewAttemptRepository(),
                    'scenario_recognition': ScenarioSubmissionRepository()}
    originals = []
    for module in earned.evidence:
        for receipt in module['assessment_snapshot']['selected_receipts']:
            repository = repositories[receipt['kind']]
            raw = await repository.records.find_one({'uuid': receipt['attempt_id'], 'user_id': learner.user_id})
            saved = repository.decode(raw)
            assert raw['record_sha256'] == receipt['record_sha256']
            assert encode(saved['result'])[1] == receipt['result_sha256']
            record = saved['record'] if receipt['kind'] == 'automatic_review' else saved
            assert record['module_id'] == module['module_id']
            assert record['enrollment_id'] == earned.enrollment_id
            assert record['manifest_sha256'] == earned.manifest_sha256
            if receipt['kind'] == 'automatic_review':
                assert record['evidence'] and record['provenance'] and record['reviewer']
                assert record['contract'] == package_outcomes(package).model_dump(mode='json')
            else:
                bank = module_bank(package, module['module_id'])
                assert record['bank_sha256'] == bank.digest
                assert record['result'] == bank.grade(record['answers'], expected_sha256=bank.digest)
            originals.append((repository, raw, saved))

    assert sum(isinstance(repository, ReviewAttemptRepository) for repository, _, _ in originals) == 10
    assert {item['module_id'] for item in earned.evidence} == {module.id for module in package.manifest.modules}
    original_credential = earned.model_dump_json()
    # Ordinary live edits cannot alter already assessed values or configurations.
    for model, changes in ((SmartDocument, {'raw_text': 'Later replacement source', 'title': 'Later title'}),
                           (SearchSetItem, {'searchphrase': 'Later field instruction'}),
                           (Workflow, {'title': 'Later workflow title'})):
        await model.get_motor_collection().update_many({}, {'$set': changes})
    for repository, raw, saved in originals:
        assert await repository.get(learner.user_id, raw['uuid']) == saved

    removed = {}
    for model in (SmartDocument, SearchSet, SearchSetItem, Workflow, WorkflowStep, WorkflowStepTask,
                  CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision,
                  CertificationProcessSubmission, CertificationWorkflowDesignSubmission):
        result = await model.get_motor_collection().delete_many({})
        removed[model.__name__] = result.deleted_count
    assert removed['SmartDocument'] and removed['CertificationLabExecution'] and removed['CertificationLearnerDecision']
    for repository, raw, saved in originals:
        assert await repository.records.find_one({'uuid': raw['uuid']}) == raw
        assert await repository.get(learner.user_id, raw['uuid']) == saved
        assert await repository.get('foreign', raw['uuid']) is None
        if isinstance(repository, ReviewAttemptRepository):
            public = await ReviewDelivery(repo).get(learner.user_id, learner.uuid, raw['uuid'])
            assert public['attempt_id'] == raw['uuid']
    assert (await CredentialRepository().for_enrollment(learner.user_id, learner.uuid)).model_dump_json() == original_credential
    return originals, removed


@pytest.mark.parametrize('lost_issuance', [False, True])
async def test_full_course_requires_all_original_outcomes_and_graduates_once(repo, monkeypatch, tmp_path, lost_issuance):
    authored = candidate.__wrapped__(tmp_path)
    path = authored.folder.parent / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    path.write_text(json.dumps(registry))
    repo.catalog = CourseCatalog(authored.folder.parent)
    original_name = 'Dr. Alexandra Theodora Wilhelmina Featherstonehaugh-Cholmondeley, Synthetic Certification QA Learner'
    profile = await User(user_id='full-course-learner', name=original_name, email='full-course@example.test').insert()
    learner = await repo.ensure_initial('full-course-learner')
    package = repo.catalog.load(VERSION)
    pinned_manifest = hashlib.sha256((authored.folder / 'manifest.json').read_bytes()).hexdigest()
    enrolled = (learner, package)
    # Reuse workspace/action fixtures, skipping their per-test course authoring.
    # All source captures and actions are now created in this original enrollment.
    for module in (budget_inputs, output_inputs, batch_inputs, validation_inputs, governance_inputs):
        monkeypatch.setattr(module, 'fixture', partial(module.fixture, enrolled=enrolled))
    for name in ('extraction_repair_fixture', 'process_design_fixture', 'connected_workflow_fixture'):
        monkeypatch.setattr(base, name, partial(getattr(base, name), enrolled=enrolled))
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    hooks = AsyncMock()
    monkeypatch.setattr('app.services.certification_service._fire_certification_complete_hooks', hooks)
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=learner.user_id)
    judge = AsyncMock(side_effect=base.supported_review)
    expected_xp = 0
    outcomes = set()
    credentials = CredentialRepository()
    contract = package_outcomes(package)
    completed_requests = []
    pending_credential = None
    # Deliberately reverse suggested order; no prerequisite access override.
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        introduction = await client.get('/certification/course', params={'enrollment_id': learner.uuid})
        assert introduction.status_code == 200
        course_scope = introduction.json()['credential_scope']
        assert course_scope['promise'] == contract.credential_promise
        assert course_scope['agent_assistance'] == contract.agent_assistance
        assert course_scope['exclusions'] == list(contract.exclusions)
        for index, module in enumerate(reversed(package.manifest.modules)):
            prepared = await review_for(module.id, repo, learner, package, monkeypatch)
            selection = {}
            if prepared:
                selection['review_attempt_id'] = prepared['attempt_id']
                reviewed = await base.evaluate_review(repo, learner, package, prepared['attempt_id'], judge)
                assert reviewed['result']['assessment']['status'] == 'requirements_supported', module.id
            required = next(m for m in contract.modules if m.module_id == module.id)
            if any(o.method == 'scenario_choice' for o in required.outcomes):
                bank = module_bank(package, module.id)
                selection['scenario_attempt_id'] = uuid4().hex
                await base.submit_scenario(repo, learner, package, bank,
                    {q.id: q.correct_choice_id for q in bank.questions}, selection['scenario_attempt_id'])
            params = {'enrollment_id': learner.uuid, 'request_id': uuid4().hex}
            body = {'consent': 'complete_selected_saved_outcomes', **selection}
            endpoint = f'/certification/modules/{module.id}/complete'
            if module.id == 'governance':
                # Complete practical capstone work alone cannot replace its
                # separately required recognition outcome.
                incomplete = {key: value for key, value in body.items() if key != 'scenario_attempt_id'}
                refused = await client.post(endpoint,
                    params={**params, 'request_id': uuid4().hex}, json=incomplete)
                assert refused.status_code == 400, refused.text
                assert (await repo.read_progress(learner.user_id, learner.uuid)).total_xp == 0
                assert await credentials.for_enrollment(learner.user_id, learner.uuid) is None
            if index == 10 and lost_issuance:
                async def unavailable(*args, **kwargs):
                    raise RuntimeError('Synthetic full-course issuance interruption')
                with monkeypatch.context() as interrupted:
                    interrupted.setattr(CredentialRepository, 'persist', unavailable)
                    with pytest.raises(RuntimeError, match='full-course issuance interruption'):
                        await client.post(endpoint, params=params, json=body)
                preserved = await repo.read_progress(learner.user_id, learner.uuid)
                pending_credential = preserved.pending_credential
                assert preserved.total_xp == 1850 and preserved.certified
                assert len(pending_credential['outcomes']) == 33
                assert await credentials.for_enrollment(learner.user_id, learner.uuid) is None
                # Fresh repository instances read original durable state.
                repo.catalog = CourseCatalog(authored.folder.parent)
                credentials = CredentialRepository()
            response = await client.post(endpoint, params=params, json=body)
            assert response.status_code == 200, (module.id, response.text)
            assert response.json()['xp_earned'] == module.base_xp, (module.id, response.json())
            expected_xp += module.base_xp
            progress = await repo.read_progress(learner.user_id, learner.uuid)
            assert progress.total_xp == expected_xp
            assert progress.certified is (index == 10)
            assert bool(await credentials.for_enrollment(learner.user_id, learner.uuid)) is (index == 10)
            credit = progress.modules[module.id]
            snapshot = verified_credit_snapshot(package, progress, module.id, credit['outcome_credit'],
                expected_attempt_id=params['request_id'])
            assert snapshot['all_required_outcomes_supported'] and len(snapshot['outcomes']) == 3
            outcomes.update(o.id for o in required.outcomes)
            assert (await client.post(endpoint, params=params, json=body)).json() == response.json()
            completed_requests.append((endpoint, params, body, response.json()))
            assert hashlib.sha256((authored.folder / 'manifest.json').read_bytes()).hexdigest() == pinned_manifest
        earned = await credentials.for_enrollment(learner.user_id, learner.uuid)
        assert earned.schema_version == 2
        assert earned.credential_scope.model_dump(mode='json') == {key: value for key, value in course_scope.items() if key != 'state'}
        original_credential = earned.model_dump_json()
        if pending_credential:
            assert earned.model_dump(mode='json') == pending_credential
        assert len(outcomes) == len(earned.outcomes) == 33
        assert len(earned.module_ids) == len(earned.evidence) == 11
        assert expected_xp == 1850
        completed_progress = await repo.read_progress(learner.user_id, learner.uuid)
        original_modules = json.dumps(completed_progress.modules, sort_keys=True, default=str)
        for endpoint, params, body, original_result in completed_requests:
            assert (await client.post(endpoint, params=params, json=body)).json() == original_result
        assert (await credentials.for_enrollment(learner.user_id, learner.uuid)).model_dump_json() == original_credential
        assert await credentials.records.count_documents({}) == 1
        # Eleven applied completions plus the saved no-credit capstone attempt.
        assert await CertificationAttempt.get_motor_collection().count_documents({}) == 12
        assert await repo.enrollments.count_documents({}) == 1
        final = await repo.read_progress(learner.user_id, learner.uuid)
        assert final.total_xp == 1850 and final.pending_credential is None
        assert json.dumps(final.modules, sort_keys=True, default=str) == original_modules
        assert (await repo.enrollments.find_one({'uuid': learner.uuid}))['state'] == 'completed'
        path = f'/certification/credentials/{earned.credential_id}/certificate'
        download = await client.get(path)
        assert download.status_code == 200 and download.headers['content-type'] == 'application/pdf'
        assert earned.credential_id in download.headers['content-disposition']
        with fitz.open(stream=download.content, filetype='pdf') as document:
            assert document.page_count == 1
            text = document[0].get_text()
            normalized = ' '.join(text.split())
            assert original_name in normalized
            assert earned.course_version in normalized and earned.course_title in normalized
            assert 'completed all 11 modules' in normalized
            assert earned.credential_id.upper() in normalized
            assert ' '.join(earned.credential_scope.promise.split()) in normalized
            assert all(document[0].rect.contains(fitz.Rect(word[:4])) for word in document[0].get_text('words'))
        profile.name = 'Later profile name must not replace original issuance'
        await profile.save()
        preserved_assessments, removed_records = await preserve_awarded_evidence_after_workspace_deletion(
            repo, learner, package, earned)
        def unavailable_catalog(*args, **kwargs):
            raise AssertionError('Credential retrieval must not read the current catalog')
        with monkeypatch.context() as unavailable:
            unavailable.setattr(CourseCatalog, 'load', unavailable_catalog)
            for repository, raw, saved in preserved_assessments:
                assert await repository.get(learner.user_id, raw['uuid']) == saved
            listing = await client.get('/certification/credentials')
            assert listing.status_code == 200
            assert listing.json()['credentials'][0]['learner_name'] == original_name
            assert listing.json()['credentials'][0]['credential_scope'] == earned.credential_scope.model_dump(mode='json')
            recovered_download = await client.get(path)
            assert recovered_download.status_code == 200
            with fitz.open(stream=recovered_download.content, filetype='pdf') as document:
                assert document[0].get_text() == text
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='foreign')
            assert (await client.get(path)).status_code == 404
            app.dependency_overrides.clear()
            assert (await client.get(path)).status_code == 401
        evidence_directory = os.environ.get('CERTIFICATION_FULL_COURSE_EVIDENCE_DIR')
        if evidence_directory:
            destination = Path(evidence_directory)
            destination.mkdir(parents=True, exist_ok=True)
            variant = 'recovered' if lost_issuance else 'normal'
            (destination / f'certificate-{variant}.pdf').write_bytes(download.content)
            (destination / f'certificate-{variant}.json').write_text(json.dumps({
                'credential_id': earned.credential_id, 'learner_name': earned.learner_name,
                'course_title': earned.course_title, 'course_version': earned.course_version,
                'manifest_sha256': earned.manifest_sha256, 'certified_at': earned.certified_at,
                'required_modules': len(earned.module_ids), 'required_outcomes': len(earned.outcomes),
                'credential_scope': earned.credential_scope.model_dump(mode='json'),
                'credential_summary': listing.json()['credentials'][0],
                'pdf_sha256': hashlib.sha256(download.content).hexdigest(),
                'text_after_profile_and_catalog_change_unchanged': True,
                'assessed_evidence_survives_workspace_edits_and_deletion': True,
                'preserved_assessment_receipts': len(preserved_assessments),
                'removed_fixture_records': removed_records,
                'foreign_status': 404, 'unauthenticated_status': 401,
                'fixture_only': True, 'providers_stubbed': True,
            }, indent=2) + '\n')
    assert judge.await_count == 10
