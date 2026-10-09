import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.certification_versions.scenario_assessment import ScenarioBank
from app.services.certification_versions.outcomes import OutcomeContract

DATA = Path(__file__).resolve().parents[1] / 'certification-data'
DRAFT = DATA / 'drafts/v5.0'
BANK = ScenarioBank.model_validate_json((DRAFT / 'ai-literacy-scenarios.json').read_bytes())


def answers():
    return {question.id: question.correct_choice_id for question in BANK.questions}


def test_recognition_results_cover_the_three_declared_ai_literacy_outcomes_without_awarding_credit():
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    ai = next(module for module in contract.modules if module.module_id == 'ai_literacy')
    assert set(BANK.outcome_ids) == {outcome.id for outcome in ai.outcomes}
    assert BANK.rubric_id == contract.rubric_id
    BANK.verify_contract(contract)
    result = BANK.grade(answers(), expected_sha256=BANK.digest)
    assert result['passed'] is True
    assert result['credit_awarded'] is False
    assert len(result['checks']) == 9
    assert all(check['role'] == 'required' for check in result['checks'])
    assert all(outcome['passed'] for outcome in result['outcomes'])


@pytest.mark.parametrize('question_id,wrong_choice', [
    (question.id, choice.id) for question in BANK.questions for choice in question.choices if choice.id != question.correct_choice_id
])
def test_every_critical_wrong_choice_fails_its_outcome_even_when_other_answers_are_correct(question_id, wrong_choice):
    submitted = {**answers(), question_id: wrong_choice}
    result = BANK.grade(submitted, expected_sha256=BANK.digest)
    assert result['passed'] is False
    failed = [check for check in result['checks'] if not check['passed']]
    assert len(failed) == 1
    assert failed[0]['id'] == question_id
    assert failed[0]['detail']
    assert [outcome['outcome_id'] for outcome in result['outcomes'] if not outcome['passed']] == [failed[0]['outcome_id']]
    assert result['credit_awarded'] is False


def test_missing_answers_are_incomplete_not_implicit_success():
    result = BANK.grade({}, expected_sha256=BANK.digest)
    assert result['passed'] is False
    assert not any(outcome['passed'] for outcome in result['outcomes'])
    assert all('Choose an answer' in check['detail'] for check in result['checks'])


@pytest.mark.parametrize('submitted', [{'unknown_question': 'verify'}, {BANK.questions[0].id: 'unknown_choice'}])
def test_unknown_submission_identities_are_rejected(submitted):
    with pytest.raises(ValueError, match='unknown'):
        BANK.grade(submitted, expected_sha256=BANK.digest)


def test_changed_requirement_digest_cannot_grade_an_old_submission():
    with pytest.raises(ValueError, match='pinned assessment bank'):
        BANK.grade(answers(), expected_sha256='0' * 64)


def test_public_definition_does_not_expose_answer_keys_or_feedback():
    public = BANK.public_definition()
    assert public['bank_sha256'] == BANK.digest
    for question in public['questions']:
        assert set(question) == {'id', 'prompt', 'choices'}
        assert all(set(choice) == {'id', 'text'} for choice in question['choices'])


def test_scenario_bank_cannot_claim_another_rubric_or_structured_review_outcome():
    raw = json.loads((DRAFT / 'outcomes.json').read_text())
    raw['rubric_id'] = 'different-rubric'
    with pytest.raises(ValueError, match='declared recognition outcomes'):
        BANK.verify_contract(OutcomeContract.model_validate(raw))
    raw['rubric_id'] = BANK.rubric_id
    raw['modules'][0]['outcomes'][0]['method'] = 'structured_review'
    with pytest.raises(ValueError, match='declared recognition outcomes'):
        BANK.verify_contract(OutcomeContract.model_validate(raw))


@pytest.mark.parametrize('mutation', ['missing_coverage', 'duplicate_question', 'duplicate_choice', 'invalid_key'])
def test_invalid_scenario_bank_cannot_be_loaded(mutation):
    raw = BANK.model_dump(mode='json')
    if mutation == 'missing_coverage':
        raw['questions'] = [question for question in raw['questions'] if question['outcome_id'] != raw['outcome_ids'][0]]
    elif mutation == 'duplicate_question':
        raw['questions'].append(raw['questions'][0])
    elif mutation == 'duplicate_choice':
        raw['questions'][0]['choices'].append(raw['questions'][0]['choices'][0])
    else:
        raw['questions'][0]['correct_choice_id'] = 'not_a_choice'
    with pytest.raises(ValidationError):
        ScenarioBank.model_validate(raw)


@pytest.mark.parametrize('module_id', ['ai_literacy', 'foundations', 'process_mapping', 'workflow_design', 'extraction_engine', 'multi_step', 'advanced_nodes', 'output_delivery', 'validation_qa', 'batch_processing', 'governance'])
def test_draft_teaching_replaces_known_lessons_with_explicit_new_revisions(module_id):
    draft = json.loads((DRAFT / f"{module_id.replace('_', '-')}-teaching.json").read_text())
    old = {lesson['id']: lesson for lesson in json.loads((DATA / 'lessons.json').read_text())[module_id]['lessons']}
    assert draft['state'] == 'design_draft'
    assert [lesson['id'] for lesson in draft['replacements']] == list(old)
    assert draft['module_patch']['objectives']
    for lesson in draft['replacements']:
        assert lesson['id'] in old
        assert lesson['revision'] > old[lesson['id']]['revision']
        assert lesson['variant'] in {'concept', 'walkthrough', 'key-terms', 'insight'}
        assert len(lesson['content']) > 500
        assert sum(choice['correct'] for choice in lesson['knowledge_check']['options']) == 1


REMAINING_BANKS = [ScenarioBank.model_validate_json((DRAFT / name).read_bytes()) for name in (
    'validation-qa-scenarios.json', 'governance-scenarios.json')]


def test_every_declared_recognition_outcome_has_exactly_one_draft_bank():
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    banks = [BANK, *REMAINING_BANKS]
    expected = {outcome.id for module in contract.modules for outcome in module.outcomes if outcome.method == 'scenario_choice'}
    actual = [outcome for bank in banks for outcome in bank.outcome_ids]
    assert set(actual) == expected
    assert len(actual) == len(set(actual))
    for bank in banks:
        bank.verify_contract(contract)


@pytest.mark.parametrize('bank', REMAINING_BANKS, ids=lambda bank: bank.module_id)
def test_mixed_module_recognition_only_reports_its_own_outcomes_without_credit(bank):
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    module = next(module for module in contract.modules if module.module_id == bank.module_id)
    result = bank.grade({q.id: q.correct_choice_id for q in bank.questions}, expected_sha256=bank.digest)
    assert result['passed'] is True
    assert result['credit_awarded'] is False
    assert {item['outcome_id'] for item in result['outcomes']} == set(bank.outcome_ids)
    assert set(bank.outcome_ids) < {outcome.id for outcome in module.outcomes}
    assert 'correct_choice_id' not in json.dumps(bank.public_definition())
    assert 'feedback' not in json.dumps(bank.public_definition())
    missing = bank.grade({}, expected_sha256=bank.digest)
    assert missing['passed'] is False
    assert all(not check['passed'] for check in missing['checks'])


@pytest.mark.parametrize('bank,question,choice', [
    (bank, question, choice) for bank in REMAINING_BANKS for question in bank.questions
    for choice in question.choices if choice.id != question.correct_choice_id
], ids=lambda value: getattr(value, 'id', getattr(value, 'module_id', None)))
def test_remaining_recognition_critical_errors_cannot_be_averaged_into_a_pass(bank, question, choice):
    submitted = {q.id: q.correct_choice_id for q in bank.questions}
    submitted[question.id] = choice.id
    result = bank.grade(submitted, expected_sha256=bank.digest)
    assert result['passed'] is False
    assert result['credit_awarded'] is False
    failed = [check for check in result['checks'] if not check['passed']]
    assert len(failed) == 1
    assert failed[0]['id'] == question.id
    assert failed[0]['detail'] == choice.feedback
    assert result['outcomes'] == [{'outcome_id': question.outcome_id, 'passed': False}]
