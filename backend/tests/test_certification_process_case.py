"""Validate the authored design task, not a learner's competence or a live judge."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.process_case import ProcessMappingCase

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'process-mapping-case.json').read_text())


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


def test_task_is_self_contained_and_does_not_expose_private_review_guidance(design):
    case = ProcessMappingCase.model_validate(design)
    case.verify_contract(contract())
    case.verify_exercise(json.loads((DRAFT / 'process-mapping-exercise.json').read_text()))
    public = case.public_definition()
    assert public['provenance'] == 'authored_fictional_design_case_not_execution'
    assert len(public['assigned_inputs']) == 3 and len(public['questions']) == 3
    assert len(public['method_comparisons']) == 3
    assert 'review_guidance' not in public
    assert 'case_application' not in json.dumps(public)
    assert 'passing_conditions' not in json.dumps(public)
    assert public['case_sha256'] == case.digest
    assert all(outcome.assessment_status == 'implemented' for module in contract().modules
               if module.module_id == 'process_mapping' for outcome in module.outcomes)


@pytest.mark.parametrize('change', ['execution_claim', 'injected_run', 'duplicate_input', 'duplicate_question',
    'missing_comparison', 'duplicate_comparison', 'missing_method', 'duplicate_method', 'foreign_outcome',
    'duplicate_guide', 'wrong_response', 'staff_review', 'presence_credit', 'forced_personal_work'])
def test_rejects_ambiguous_assets_and_changed_assessment_boundaries(design, change):
    if change == 'execution_claim':
        design['provenance'] = 'actual_learner_execution'
    elif change == 'injected_run':
        design['run_id'] = 'a' * 32
    elif change == 'duplicate_input':
        design['assigned_inputs'].append(design['assigned_inputs'][0])
    elif change == 'duplicate_question':
        design['questions'][1]['id'] = design['questions'][0]['id']
    elif change == 'missing_comparison':
        design['method_comparisons'].pop()
    elif change == 'duplicate_comparison':
        design['method_comparisons'][1] = design['method_comparisons'][0]
    elif change == 'missing_method':
        design['method_options'].pop()
    elif change == 'duplicate_method':
        design['method_options'].append(design['method_options'][0])
    elif change == 'foreign_outcome':
        design['questions'][0]['outcome_id'] = 'workflow_design.data_flow'
    elif change == 'duplicate_guide':
        design['review_guidance'][1] = design['review_guidance'][0]
    elif change == 'wrong_response':
        design['questions'][1]['response_kind'] = 'method_and_rationale'
    elif change == 'staff_review':
        design['assessment_policy'] = 'staff_queue'
    elif change == 'presence_credit':
        design['assessment_policy'] = 'nonempty_answers_pass'
    else:
        design['handoff_policy'] = 'require_personal_process'
    with pytest.raises(ValidationError):
        ProcessMappingCase.model_validate(design)


@pytest.mark.parametrize('change', ['passing_condition', 'critical_failure', 'wrong_method', 'missing_outcome'])
def test_case_cannot_weaken_or_replace_the_declared_rubric(design, change):
    value = contract().model_dump(mode='json')
    module = next(module for module in value['modules'] if module['module_id'] == 'process_mapping')
    if change == 'passing_condition':
        design['review_guidance'][0]['passing_conditions'] = ['Any nonempty rationale establishes successful method choice.']
    elif change == 'critical_failure':
        design['review_guidance'][1]['critical_failures'] = ['Only a missing map title constitutes a critical failure.']
    elif change == 'wrong_method':
        module['outcomes'][0]['method'] = 'scenario_choice'
    else:
        module['outcomes'].pop()
    with pytest.raises(ValueError):
        ProcessMappingCase.model_validate(design).verify_contract(OutcomeContract.model_validate(value))


@pytest.mark.parametrize('change', ['documents', 'expected_fields', 'expected_values', 'star_criteria',
                                     'assessment_case_id', 'process_case_sha256', 'assessment_method'])
def test_exercise_cannot_reintroduce_legacy_reflection_credit_or_another_assignment(design, change):
    exercise = json.loads((DRAFT / 'process-mapping-exercise.json').read_text())
    wrong = {'documents': ['personal-report.pdf'], 'expected_fields': ['arbitrary field'],
             'expected_values': {'answer': 'approved'}, 'star_criteria': {'3': 'Write any reflection'},
             'assessment_case_id': 'different-case', 'process_case_sha256': 'f' * 64,
             'assessment_method': 'legacy_reflection'}
    exercise[change] = wrong[change]
    with pytest.raises(ValueError):
        ProcessMappingCase.model_validate(design).verify_exercise(exercise)


@pytest.mark.parametrize('section', ['task', 'flawed_proposal', 'review_guidance'])
def test_case_identity_changes_with_task_proposal_or_private_guidance(design, section):
    original = ProcessMappingCase.model_validate(design)
    changed = deepcopy(design)
    if section == 'review_guidance':
        changed[section][0]['case_application'] += ' Additional reviewed authoring guidance.'
    else:
        changed[section] += ' Additional authored requirement.'
    assert ProcessMappingCase.model_validate(changed).digest != original.digest
    assert ProcessMappingCase.model_validate(json.loads(json.dumps(design))).digest == original.digest


@pytest.mark.parametrize('change', [None, 'missing', 'exercise', 'rubric', 'module'])
def test_package_loader_checks_case_exercise_and_rubric_together(design, monkeypatch, change):
    from types import SimpleNamespace
    from app.services.certification_versions import outcomes
    from app.services.certification_versions.catalog import CourseCatalogError
    from app.services.certification_versions.process_case import load_process_case
    assets = {'process-cases/process_mapping.json': design,
              'exercises.json': {'process_mapping': json.loads((DRAFT / 'process-mapping-exercise.json').read_text())}}
    package = SimpleNamespace(manifest=SimpleNamespace(artifacts={'process-cases/process_mapping.json': 'a' * 64}), json=assets.__getitem__)
    monkeypatch.setattr(outcomes, 'package_outcomes', lambda _: contract())
    if change is None:
        assert load_process_case(package).digest == ProcessMappingCase.model_validate(design).digest
        return
    if change == 'missing':
        package.manifest.artifacts.clear()
    elif change == 'exercise':
        assets['exercises.json']['process_mapping']['star_criteria'] = {'3': 'Answer every reflection'}
    elif change == 'rubric':
        design['review_guidance'][0]['passing_conditions'] = ['Give any answer, with no evidence or rationale required.']
    else:
        design['module_id'] = 'foundations'
    with pytest.raises(CourseCatalogError):
        load_process_case(package)


@pytest.mark.parametrize('change', ['actor', 'credit', 'wrong_consent', 'blank', 'oversize', 'wrong_reference', 'missing_answer'])
def test_submission_schema_cannot_assert_actor_credit_or_skip_explicit_design_consent(change):
    from app.services.certification_versions.process_submissions import ProcessSubmission
    body = {'request_id': 'a' * 32, 'case_sha256': 'b' * 64, 'consent': 'save_reviewed_process_design',
            'answers': {'method_choice': 'An unresolved choice.', 'human_checkpoint': 'An incomplete map.', 'bounded_scope': 'An unresolved scope.'}}
    if change == 'actor':
        body['actor_user_id'] = 'staff'
    elif change == 'credit':
        body['credit_awarded'] = True
    elif change == 'wrong_consent':
        body['consent'] = 'execute_workflow'
    elif change == 'blank':
        body['answers']['human_checkpoint'] = '   '
    elif change == 'oversize':
        body['answers']['human_checkpoint'] = 'x' * 12001
    elif change == 'wrong_reference':
        body['previous_submission_id'] = 'another course'
    else:
        body['answers'].pop('bounded_scope')
    with pytest.raises(ValidationError):
        ProcessSubmission.model_validate(body)
