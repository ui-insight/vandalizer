"""The authored assignment must not claim saved artifacts, runs or earned credit."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.process_case import ProcessMappingCase
from app.services.certification_versions.workflow_design_case import WorkflowDesignCase

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'workflow-design-case.json').read_text())


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


def process():
    return ProcessMappingCase.model_validate_json((DRAFT / 'process-mapping-case.json').read_bytes())


def test_supplied_map_is_authored_and_review_guidance_is_private(design):
    case = WorkflowDesignCase.model_validate(design)
    case.verify_contract(contract())
    case.verify_process_case(process())
    case.verify_exercise(json.loads((DRAFT / 'workflow-design-exercise.json').read_text()))
    public = case.public_definition()
    assert public['supplied_map']['provenance'] == 'authored_example_not_learner_work'
    assert set(public['handoff_choices']) == {'owned_saved_process_submission', 'supplied_example'}
    assert public['artifact_policy'] == 'owned_saved_workflow_snapshot_not_reflection_or_step_count'
    assert public['case_sha256'] == case.digest
    assert 'review_guidance' not in public and 'passing_conditions' not in json.dumps(public)
    assert all(o.assessment_status == 'implemented' for m in contract().modules
               if m.module_id == 'workflow_design' for o in m.outcomes)


@pytest.mark.parametrize('change', ['execution_claim', 'fake_artifact', 'staff_task', 'presence_credit',
    'reflection_only', 'implicit_approval', 'missing_example', 'duplicate_handoff', 'credit_transfer',
    'duplicate_question', 'foreign_outcome', 'wrong_response', 'duplicate_guide', 'duplicate_input', 'fake_learner_map'])
def test_rejects_fabricated_evidence_and_weakened_boundaries(design, change):
    if change == 'execution_claim':
        design['provenance'] = 'successful_workflow_execution'
    elif change == 'fake_artifact':
        design['artifact_id'] = 'a' * 24
    elif change == 'staff_task':
        design['execution_policy'] = 'send_to_staff_for_approval'
    elif change == 'presence_credit':
        design['assessment_policy'] = 'nonempty_answers_pass'
    elif change == 'reflection_only':
        design['artifact_policy'] = 'accept_client_diagram'
    elif change == 'implicit_approval':
        design['assistance_policy'] = 'agent_may_approve'
    elif change == 'missing_example':
        design['handoff_choices'].pop()
    elif change == 'duplicate_handoff':
        design['handoff_choices'].append('supplied_example')
    elif change == 'credit_transfer':
        design['handoff_policy'] = 'map_implies_pass'
    elif change == 'duplicate_question':
        design['questions'][1] = design['questions'][0]
    elif change == 'foreign_outcome':
        design['questions'][0]['outcome_id'] = 'process_mapping.method_choice'
    elif change == 'wrong_response':
        design['questions'][0]['response_kind'] = 'correct_then_approve_design'
    elif change == 'duplicate_guide':
        design['review_guidance'][1] = design['review_guidance'][0]
    elif change == 'duplicate_input':
        design['assigned_inputs'].append(design['assigned_inputs'][0])
    else:
        design['supplied_map']['provenance'] = 'approved_learner_submission'
    with pytest.raises(ValidationError):
        WorkflowDesignCase.model_validate(design)


@pytest.mark.parametrize('change', ['passing_conditions', 'critical_failures', 'prose_only', 'wrong_method', 'missing_outcome'])
def test_review_must_preserve_rubric_and_actual_artifact_requirements(design, change):
    value = contract().model_dump(mode='json')
    module = next(m for m in value['modules'] if m['module_id'] == 'workflow_design')
    if change in ('passing_conditions', 'critical_failures'):
        design['review_guidance'][0][change] = ['A learner claim is sufficient even without a saved configuration.']
    elif change == 'prose_only':
        module['outcomes'][0]['evidence'] = ['learner_decision']
    elif change == 'wrong_method':
        module['outcomes'][0]['method'] = 'scenario_choice'
    else:
        module['outcomes'].pop()
    with pytest.raises(ValueError):
        WorkflowDesignCase.model_validate(design).verify_contract(OutcomeContract.model_validate(value))


@pytest.mark.parametrize('change', ['hash', 'id', 'inputs', 'output', 'scope'])
def test_handoff_cannot_silently_substitute_another_process_case(design, change):
    if change == 'hash':
        design['source_process_case_sha256'] = 'a' * 64
    elif change == 'id':
        design['source_process_case_id'] = 'another-case'
    elif change == 'inputs':
        design['assigned_inputs'][0]['description'] = 'A different source was substituted without the learner choosing it.'
    elif change == 'output':
        design['intended_output'] = 'An externally released institutional determination.'
    else:
        design['exclusions'].pop()
    with pytest.raises(ValueError, match='preserve its exact source'):
        WorkflowDesignCase.model_validate(design).verify_process_case(process())


@pytest.mark.parametrize('change', ['documents', 'fields', 'answers', 'stars', 'case', 'hash', 'method'])
def test_exercise_rejects_legacy_credit_and_case_mismatch(design, change):
    exercise = json.loads((DRAFT / 'workflow-design-exercise.json').read_text())
    key, replacement = {
        'documents': ('documents', ['unassigned.pdf']), 'fields': ('expected_fields', ['any_field']),
        'answers': ('expected_values', {'reflection': 'filled'}), 'stars': ('star_criteria', {'3': 'four answers'}),
        'case': ('assessment_case_id', 'wrong-case'), 'hash': ('design_case_sha256', 'a' * 64),
        'method': ('assessment_method', 'reflection_presence'),
    }[change]
    exercise[key] = replacement
    with pytest.raises(ValueError, match='bind its case'):
        WorkflowDesignCase.model_validate(design).verify_exercise(exercise)


@pytest.mark.parametrize('change', ['map', 'proposal', 'private_guidance'])
def test_identity_pins_public_examples_and_private_review_requirements(design, change):
    original = WorkflowDesignCase.model_validate(design).digest
    if change == 'map':
        design['supplied_map']['ordered_process_map'] += ' Preserve this amended map as a separate authored revision.'
    elif change == 'proposal':
        design['flawed_proposal'] += ' This amendment adds a different proposed destination.'
    else:
        design['review_guidance'][0]['case_application'] += ' Require a more specific comparison of input boundaries.'
    assert WorkflowDesignCase.model_validate(design).digest != original
