from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.certification_versions.advanced_case import AdvancedNodesCase
from app.services.certification_versions.advanced_calculations import CalculationRecord, check_budget_calculations
from app.services.certification_versions.advanced_calculation_records import AdvancedCalculationSubmission

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def case():
    return AdvancedNodesCase.model_validate_json((DRAFT / 'advanced-nodes-case.json').read_bytes())


@pytest.fixture
def records(case):
    amounts = {amount.id: amount for amount in case.amounts}
    return [{'id': check.id, 'operation': 'sum', 'method': 'explicit_learner_arithmetic', 'unit': 'USD',
             'result': check.expected_value, 'interpretation': 'Addition of printed amounts only; period and policy assumptions remain unresolved.',
             'inputs': [{'id': name, 'value': amounts[name].value, 'unit': 'USD', 'source_page': amounts[name].anchor.page,
                         'source_quote': amounts[name].anchor.quote, 'status': 'supported',
                         'explanation': 'I checked the named row and printed amount.'} for name in check.inputs]}
            for check in case.calculations]


def check(case, records, source=None):
    return check_budget_calculations(case, records, source_bytes=source if source is not None else
                                     (DRAFT / 'documents' / case.source_filename).read_bytes())


@pytest.mark.parametrize('change', ['request_id', 'case_sha256', 'document_id', 'previous_snapshot_id',
                                  'self_revision', 'consent', 'duplicate', 'missing', 'actor', 'grade', 'model'])
def test_submission_requires_explicit_identity_consent_and_no_client_authority(case, records, change):
    body = {'request_id': 'a' * 32, 'case_sha256': case.digest, 'document_id': 'b' * 32,
            'records': records, 'consent': 'save_source_bound_budget_calculations'}
    if change in ('request_id', 'case_sha256', 'document_id', 'previous_snapshot_id'):
        body[change] = 'invalid'
    elif change == 'self_revision':
        body['previous_snapshot_id'] = body['request_id']
    elif change == 'consent':
        body['consent'] = 'run_and_grade'
    elif change == 'duplicate':
        body['records'][1] = deepcopy(body['records'][0])
    elif change == 'missing':
        body['records'].pop()
    else:
        body[{'actor': 'user_id', 'grade': 'credit_awarded', 'model': 'model'}[change]] = 'client supplied'
    with pytest.raises(ValidationError):
        AdvancedCalculationSubmission.model_validate(body)


@pytest.mark.parametrize('method', ['explicit_learner_arithmetic', 'recorded_deterministic_arithmetic'])
def test_checks_exact_addition_without_claiming_policy_or_workflow_success(case, records, method):
    for record in records:
        record['method'] = method
    original = deepcopy(records)
    result = check(case, records)
    assert records == original
    assert result['all_arithmetic_supported'] is True
    assert [item['computed_value'] for item in result['checks']] == ['45000.00', '517424.00', '542800.00']
    assert result['checks'][0]['expression'] == '18000.00 + 12000.00 + 15000.00'
    assert all(item['method_provenance'] == 'learner_reported' for item in result['checks'])
    assert result['interpretation_review_required'] is True
    assert result['credit_awarded'] is result['module_completion_eligible'] is False
    assert 'run_id' not in result and 'execution_receipt' not in result


def test_correct_arithmetic_on_wrong_source_values_requires_revision(case, records):
    records[0]['inputs'][0]['value'] = '19000.00'
    records[0]['result'] = '46000.00'
    result = check(case, records)
    first = result['checks'][0]
    assert first['arithmetic_matches'] is True and first['source_matches'] is False
    assert first['computed_value'] == '46000.00'  # Never silently substitute the answer key.
    assert first['state'] == 'revision_required' and result['all_arithmetic_supported'] is False


def test_wrong_final_number_is_preserved_with_actual_computation(case, records):
    records[0]['result'] = '45001.00'
    first = check(case, records)['checks'][0]
    assert first['source_matches'] is True and first['arithmetic_matches'] is False
    assert first['recorded_value'] == '45001.00' and first['computed_value'] == '45000.00'
    assert first['state'] == 'revision_required'


@pytest.mark.parametrize('change', ['fabricated_quote', 'different_row', 'wrong_page', 'missing_page'])
def test_source_quote_and_page_are_not_replaced_by_a_correct_number(case, records, change):
    operand = records[0]['inputs'][0]
    if change == 'fabricated_quote':
        operand['source_quote'] = 'Model verified the number 18000.'
    elif change == 'different_row':
        operand['source_quote'] = records[0]['inputs'][1]['source_quote']
    else:
        operand['source_page'] = 2 if change == 'wrong_page' else 999
    result = check(case, records)
    assert result['checks'][0]['arithmetic_matches'] is True
    assert result['checks'][0]['state'] == 'revision_required'
    assert result['all_arithmetic_supported'] is False


@pytest.mark.parametrize('retain_proposed_value', [False, True])
def test_unresolved_input_never_becomes_verified_from_a_matching_total(case, records, retain_proposed_value):
    operand = records[0]['inputs'][0]
    operand['status'] = 'unresolved'
    if not retain_proposed_value:
        operand['value'] = None
        operand['source_quote'] = ''
    first = check(case, records)['checks'][0]
    assert first['state'] == 'unresolved'
    assert first['computed_value'] is None and first['arithmetic_matches'] is None
    assert first['recorded_value'] == '45000.00'


def test_missing_result_is_unresolved_even_when_inputs_are_supported(case, records):
    records[0]['result'] = None
    first = check(case, records)['checks'][0]
    assert first['state'] == 'unresolved' and first['computed_value'] == '45000.00'
    assert first['arithmetic_matches'] is None


@pytest.mark.parametrize('change', ['missing_check', 'duplicate_check', 'changed_source'])
def test_rejects_missing_or_mixed_case_evidence(case, records, change):
    if change == 'missing_check':
        records.pop()
    elif change == 'duplicate_check':
        records[1] = deepcopy(records[0])
    with pytest.raises(ValueError):
        check(case, records, source=b'not the assigned PDF' if change == 'changed_source' else None)


@pytest.mark.parametrize('change', ['duplicate_input', 'omitted_input', 'wrong_order', 'nan', 'float',
                                   'eval', 'foreign_unit', 'no_quote', 'no_value', 'blank_reason', 'blank_interpretation', 'client_grade'])
def test_submission_contract_rejects_unreproducible_or_unsafe_records(records, change):
    record = records[0]
    operand = record['inputs'][0]
    if change == 'duplicate_input':
        record['inputs'][1] = deepcopy(operand)
    elif change == 'omitted_input':
        record['inputs'].pop()
    elif change == 'wrong_order':
        record['inputs'].reverse()
    elif change == 'nan':
        operand['value'] = 'NaN'
    elif change == 'float':
        operand['value'] = 18000.0
    elif change == 'eval':
        record['operation'] = '__import__("os").system("true")'
    elif change == 'foreign_unit':
        operand['unit'] = 'EUR'
    elif change == 'no_quote':
        operand['source_quote'] = ' '
    elif change == 'no_value':
        operand['value'] = None
    elif change == 'blank_reason':
        operand['explanation'] = ' ' * 20
    elif change == 'blank_interpretation':
        record['interpretation'] = ' ' * 30
    else:
        record['credit_awarded'] = True
    with pytest.raises(ValidationError):
        CalculationRecord.model_validate(record)
