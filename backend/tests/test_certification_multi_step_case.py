"""Authored material cannot stand in for actual connected-run evidence."""
import copy
import json
from pathlib import Path

import fitz
import pytest
from pydantic import ValidationError

from app.services.certification_versions.multi_step_case import MultiStepCase
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'multi-step-case.json').read_text())


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


def test_case_binds_source_rubric_and_exercise_without_claiming_release_verification(design):
    case = MultiStepCase.model_validate(design)
    case.verify_contract(contract())
    case.verify_exercise(json.loads((DRAFT / 'multi-step-exercise.json').read_text()))
    source = (DRAFT / 'documents' / case.source_filename).read_bytes()
    with fitz.open(stream=source, filetype='pdf') as document:
        assert len(document) == 2
        case.verify_source(source, [page.get_text() for page in document])
    public = case.public_definition()
    assert public['case_sha256'] == case.digest
    assert public['flawed_example']['provenance'] == 'authored_flawed_example_not_execution'
    assert public['comparison_policy'] == 'actual_original_and_corrected_owned_runs_not_authored_specimen'
    assert public['required_links'] == ['extract_to_reason', 'reason_to_format']
    assert 'review_guidance' not in public and 'source_expectations' not in public
    assert all(outcome.assessment_status == 'implemented' for module in contract().modules
               if module.module_id == 'multi_step' for outcome in module.outcomes)


@pytest.mark.parametrize('change', ['fake_execution', 'fake_run_id', 'example_as_run', 'count_credit',
    'unrelated_runs', 'staff_queue', 'scope_expansion', 'repeat_completed_writes', 'posthoc_approval',
    'wrong_question', 'duplicate_question', 'duplicate_guide', 'missing_stage', 'duplicate_stage',
    'missing_link', 'duplicate_link', 'duplicate_source', 'nonpositive_page'])
def test_rejects_fabricated_evidence_and_unsafe_shortcuts(design, change):
    if change == 'fake_execution':
        design['provenance'] = 'successful_workflow_execution'
    elif change == 'fake_run_id':
        design['flawed_example']['run_id'] = 'a' * 32
    elif change == 'example_as_run':
        design['comparison_policy'] = 'authored_example_can_replace_original_run'
    elif change == 'count_credit':
        design['execution_rule'] = 'three_steps_anywhere_pass'
    elif change == 'unrelated_runs':
        design['repair_rule'] = 'combine_unrelated_runs_and_reflections'
    elif change == 'staff_queue':
        design['assessment_policy'] = 'staff_grades_every_result'
    elif change == 'scope_expansion':
        design['scope_policy'] = 'any_personal_documents_and_real_delivery'
    elif change == 'repeat_completed_writes':
        design['recovery_rule'] = 'automatically_restart_all_completed_steps'
    elif change == 'posthoc_approval':
        design['questions'][0]['phase'] = 'after_execution'
    elif change == 'wrong_question':
        design['questions'][1]['response_kind'] = design['questions'][2]['response_kind']
    elif change == 'duplicate_question':
        design['questions'][1] = copy.deepcopy(design['questions'][0])
    elif change == 'duplicate_guide':
        design['review_guidance'][1] = copy.deepcopy(design['review_guidance'][0])
    elif change == 'missing_stage':
        design['required_stages'].pop()
    elif change == 'duplicate_stage':
        design['required_stages'][1] = design['required_stages'][0]
    elif change == 'missing_link':
        design['required_links'].pop()
    elif change == 'duplicate_link':
        design['required_links'][1] = design['required_links'][0]
    elif change == 'duplicate_source':
        design['source_expectations'][1] = copy.deepcopy(design['source_expectations'][0])
    else:
        design['source_expectations'][0]['anchors'][0]['page'] = 0
    with pytest.raises(ValidationError):
        MultiStepCase.model_validate(design)


@pytest.mark.parametrize('change', ['evidence', 'method', 'rubric', 'missing_outcome'])
def test_rubric_cannot_weaken_execution_or_quality_requirements(design, change):
    value = json.loads((DRAFT / 'outcomes.json').read_text())
    module = next(item for item in value['modules'] if item['module_id'] == 'multi_step')
    if change == 'evidence':
        module['outcomes'][0]['evidence'] = ['learner_decision']
    elif change == 'method':
        module['outcomes'][0]['method'] = 'structured_review'
    elif change == 'rubric':
        module['outcomes'][1]['passing_conditions'] = ['Any nonempty answer is sufficient.']
    else:
        module['outcomes'].pop()
    with pytest.raises(ValueError):
        MultiStepCase.model_validate(design).verify_contract(OutcomeContract.model_validate(value))


@pytest.mark.parametrize('change', ['bytes', 'quote', 'page'])
def test_original_source_identity_and_anchors_are_required(design, change):
    source = (DRAFT / 'documents/subaward-agreement.pdf').read_bytes()
    with fitz.open(stream=source, filetype='pdf') as document:
        texts = [page.get_text() for page in document]
    if change == 'bytes':
        source += b'changed'
    elif change == 'quote':
        design['source_expectations'][0]['anchors'][0]['quote'] = 'Invented institutional standard not supplied.'
    else:
        design['source_expectations'][0]['anchors'][0]['page'] = 99
    with pytest.raises(ValueError):
        MultiStepCase.model_validate(design).verify_source(source, texts)


@pytest.mark.parametrize('change', ['documents', 'expected_fields', 'expected_values', 'star_criteria', 'identity'])
def test_exercise_cannot_restore_legacy_counts_or_substitute_another_case(design, change):
    exercise = json.loads((DRAFT / 'multi-step-exercise.json').read_text())
    if change == 'documents':
        exercise[change] = ['another-source.pdf']
    elif change == 'expected_fields':
        exercise[change] = ['any-field']
    elif change in ('expected_values', 'star_criteria'):
        exercise[change] = {'five_tasks': 'pass'}
    else:
        exercise['connected_case_sha256'] = 'a' * 64
    with pytest.raises(ValueError):
        MultiStepCase.model_validate(design).verify_exercise(exercise)


@pytest.mark.parametrize('change', ['consent', 'request_id', 'workflow_id', 'case_sha256', 'artifact', 'actor', 'execution'])
def test_capture_request_cannot_supply_evidence_or_execution_authority(change):
    from app.services.certification_versions.connected_workflow_inputs import ConnectedCaptureRequest
    body = {'request_id': 'a' * 32, 'workflow_id': 'b' * 24, 'case_sha256': 'c' * 64,
            'consent': 'capture_connected_workflow_inputs'}
    if change == 'consent':
        body['consent'] = 'execute'
    elif change in ('request_id', 'workflow_id', 'case_sha256'):
        body[change] = 'invalid'
    else:
        body[change] = 'client assertion'
    with pytest.raises(ValidationError):
        ConnectedCaptureRequest.model_validate(body)


@pytest.mark.parametrize('kind', ['saved_workflow_design', 'connected_workflow_input'])
def test_workflow_snapshots_are_rejected_before_extraction_planning(kind):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.lab_execution import execution_plan
    with pytest.raises(EnrollmentConflict):
        execution_plan({'record_kind': kind}, {})
