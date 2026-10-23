from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.services.certification_versions.connected_workflow_reviews import ConnectedReviewRequest


def review_body():
    return {'request_id': 'a' * 32, 'original_run_id': 'b' * 32, 'original_result_sha256': 'c' * 64,
            'corrected_run_id': 'd' * 32, 'corrected_result_sha256': 'e' * 64, 'case_sha256': 'f' * 64,
            'answers': {'connection_repair': 'I compared the actual stage results.', 'source_review': 'The source establishes only the stated facts.'},
            'consent': 'save_connected_workflow_result_review'}


def test_review_request_preserves_exact_answers_and_optional_revision_identity():
    body = review_body()
    body['answers']['source_review'] = '  A deliberately preserved answer.\n'
    body['previous_submission_id'] = '0' * 32
    assert ConnectedReviewRequest.model_validate(body).model_dump(mode='json') == body


@pytest.mark.parametrize('change', ['missing_answer', 'extra_answer', 'wrong_answer', 'blank_answer', 'large_answer',
    'coerced_answer', 'same_run', 'missing_consent', 'wrong_consent', 'bad_request', 'bad_result', 'bad_case',
    'bad_previous', 'extra_authority'])
def test_review_request_rejects_incomplete_answers_ambiguous_identity_and_authority(change):
    body = deepcopy(review_body())
    if change == 'missing_answer':
        del body['answers']['source_review']
    elif change == 'extra_answer':
        body['answers']['scope_approval'] = 'Approve'
    elif change == 'wrong_answer':
        body['answers']['source_review_wrong'] = body['answers'].pop('source_review')
    elif change in ('blank_answer', 'large_answer', 'coerced_answer'):
        body['answers']['source_review'] = {'blank_answer': ' \n\t', 'large_answer': 'a' * 8001, 'coerced_answer': 7}[change]
    elif change == 'same_run':
        body['corrected_run_id'] = body['original_run_id']
    elif change == 'missing_consent':
        del body['consent']
    elif change == 'wrong_consent':
        body['consent'] = True
    elif change == 'bad_request':
        body['request_id'] = 'not-a-request'
    elif change == 'bad_result':
        body['corrected_result_sha256'] = 'e' * 63
    elif change == 'bad_case':
        body['case_sha256'] = 'Z' * 64
    elif change == 'bad_previous':
        body['previous_submission_id'] = ''
    else:
        body['credit_awarded'] = True
    with pytest.raises(ValidationError):
        ConnectedReviewRequest.model_validate(body)
