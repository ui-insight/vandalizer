"""Mixed course routing instructions fail the strict chat display boundary."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.services.certification_versions.tool_results import ModuleResult


def payload():
    return {'module_id': 'foundations', 'title': 'Foundations', 'xp': 150, 'completed': False, 'stars': 0,
            'overview': 'Supervise the assigned bounded extraction.', 'instructions': [], 'lesson_titles': [],
            'expected_fields': [], 'star_criteria': {}, 'sample_documents': [], 'provisioned_docs': [],
            'assessment_keys': [], 'assessment_questions': [], 'assessment_mode': 'selected_saved_outcomes',
            'selected_outcome_completion': False,
            'required_outcomes': [{'outcome_id': 'foundations.scoped_proposal',
                                   'statement': 'Check the proposed scope against the assigned task.',
                                   'method': 'structured_review'}]}


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'foreign_module', 'legacy_keys', 'legacy_questions', 'legacy_mode', 'unknown_method'])
def test_contradictory_or_foreign_assessment_instructions_are_not_delivered(change):
    body = payload()
    if change == 'missing':
        body['required_outcomes'] = []
    elif change == 'duplicate':
        body['required_outcomes'] *= 2
    elif change == 'foreign_module':
        body['required_outcomes'][0]['outcome_id'] = 'governance.scoped_proposal'
    elif change == 'legacy_keys':
        body['assessment_keys'] = ['experience']
    elif change == 'legacy_questions':
        body['assessment_questions'] = [{'key': 'experience'}]
    elif change == 'legacy_mode':
        body['assessment_mode'] = 'legacy_reflection'
    else:
        body['required_outcomes'][0]['method'] = 'staff_queue'
    with pytest.raises(ValidationError):
        ModuleResult.model_validate(body)


def test_saved_old_card_without_new_routing_metadata_remains_readable():
    body = payload()
    for key in ('required_outcomes', 'assessment_mode', 'selected_outcome_completion'):
        del body[key]
    original = deepcopy(body)
    assert ModuleResult.model_validate(body).assessment_mode is None
    assert body == original
