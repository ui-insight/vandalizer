"""Receipt summaries are validated without reassessing historical answers."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.scenario_assessment import ScenarioBank
from app.services.certification_versions.scenario_history import ScenarioHistory

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
BANKS = [ScenarioBank.model_validate_json(path.read_bytes()) for path in sorted(DRAFT.glob('*-scenarios.json'))]
ENROLLMENT = SimpleNamespace(uuid='original-course', user_id='learner', course_version='draft', manifest_sha256='a' * 64)


def seal(record):
    payload, digest = encode(record)
    return {**record, 'record_json': payload, 'record_sha256': digest}


def receipt(bank, mode='supported'):
    answers = {question.id: question.correct_choice_id if mode == 'supported' else next(choice.id for choice in question.choices if choice.id != question.correct_choice_id) for question in bank.questions} if mode != 'unanswered' else {}
    return {'uuid': 'scenario-1', 'user_id': ENROLLMENT.user_id, 'enrollment_id': ENROLLMENT.uuid,
            'course_version': ENROLLMENT.course_version, 'manifest_sha256': ENROLLMENT.manifest_sha256,
            'module_id': bank.module_id, 'request_sha256': 'b' * 64, 'bank_sha256': bank.digest,
            'submission_channel': 'authenticated_learner_request', 'answers': answers,
            'result': bank.grade(answers, expected_sha256=bank.digest)}


@pytest.mark.parametrize('bank', BANKS, ids=lambda bank: bank.module_id)
@pytest.mark.parametrize('mode', ['supported', 'incorrect', 'unanswered'])
def test_all_real_recognition_banks_preserve_saved_feedback_without_regrading(bank, mode):
    record = receipt(bank, mode)
    raw = seal(record)
    before = deepcopy(raw)
    with patch.object(ScenarioBank, 'grade', side_effect=AssertionError('Do not regrade history')):
        assert ScenarioHistory.receipt(raw, ENROLLMENT, bank) == record
    assert raw == before


@pytest.mark.parametrize('change', ['summary', 'string_pass', 'integer_check', 'missing_check', 'duplicate_check',
                                  'foreign_check', 'outcome_summary', 'missing_outcome', 'duplicate_outcome',
                                  'unknown_answer', 'foreign_outcome', 'role', 'blank_feedback', 'bank', 'rubric', 'owner', 'agent_origin',
                                  'result_list', 'outcomes_null', 'check_array'])
def test_valid_digest_does_not_hide_inconsistent_scenario_feedback(change):
    bank = BANKS[0]
    record = receipt(bank)
    result = record['result']
    if change == 'summary':
        result['passed'] = False
    elif change == 'string_pass':
        result['passed'] = 'true'
    elif change == 'integer_check':
        result['checks'][0]['passed'] = 1
    elif change == 'missing_check':
        result['checks'].pop()
    elif change == 'duplicate_check':
        result['checks'].append(deepcopy(result['checks'][0]))
    elif change == 'foreign_check':
        result['checks'][0]['id'] = 'another-case'
    elif change == 'outcome_summary':
        result['outcomes'][0]['passed'] = False
    elif change == 'missing_outcome':
        result['outcomes'].pop()
    elif change == 'duplicate_outcome':
        result['outcomes'].append(deepcopy(result['outcomes'][0]))
    elif change == 'unknown_answer':
        record['answers'][bank.questions[0].id] = 'missing-choice'
    elif change == 'foreign_outcome':
        result['checks'][0]['outcome_id'] = 'another.outcome'
    elif change == 'role':
        result['checks'][0]['role'] = 'optional'
    elif change == 'blank_feedback':
        result['checks'][0]['detail'] = ''
    elif change == 'bank':
        result['bank_id'] = 'another-bank'
    elif change == 'rubric':
        result['rubric_id'] = 'another-rubric'
    elif change == 'owner':
        record['user_id'] = 'another-learner'
    elif change == 'agent_origin':
        record['submission_channel'] = 'agent_prose'
    elif change == 'result_list':
        record['result'] = []
    elif change == 'outcomes_null':
        result['outcomes'] = None
    elif change == 'check_array':
        result['checks'][0] = []
    with patch.object(ScenarioBank, 'grade', side_effect=AssertionError('Do not regrade history')):
        with pytest.raises(CourseCatalogError):
            ScenarioHistory.receipt(seal(record), ENROLLMENT, bank)
