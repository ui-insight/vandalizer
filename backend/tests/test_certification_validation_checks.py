"""No model, badge, expectation agreement or skipped field can override sources."""
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.validation_case import ValidationCase
from app.services.certification_versions.validation_checks import canonical, check_repair, check_suite

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


def fixture():
    case = ValidationCase.model_validate_json((DRAFT / 'validation-qa-case.json').read_bytes())
    snapshot = {'user_id': 'learner', 'enrollment_id': 'course-enrollment', 'course_version': 'draft', 'manifest_sha256': 'm' * 64,
        'artifact_id': 'owned-extraction', 'case': case.public_definition(), 'artifact_sha256': 'a' * 64,
        'artifact': {'fields': [{'id': str(i), 'title': f.title, 'searchphrase': f.meaning, 'is_optional': i == 2, 'enum_values': []}
                                for i, f in enumerate(case.fields)]},
        'documents': [{'source_id': s.id, 'document_id': s.id + '-document', 'source_sha256': s.sha256, 'pages': ['Original complete source']} for s in case.sources]}
    cases = [{'source_id': s['source_id'], 'document_id': s['document_id'], 'source_sha256': s['source_sha256'],
              'source_text_sha256': encode(s['pages'])[1], 'expectations': [dict(field=e.field, expected_value=e.expected_value,
              expected_kind='value' if e.expected_value is not None else 'explicit_absence', source_references=[a.model_dump() for a in e.anchors])
              for e in case.expectations if e.source_id == s['source_id']]} for s in snapshot['documents']]
    results = [{'source_id': s['source_id'], 'source_sha256': s['source_sha256'], 'artifact_sha256': snapshot['artifact_sha256'],
                'status': 'completed', 'entities': [{field['searchphrase']: next(e.expected_value for e in case.expectations
                    if e.source_id == s['source_id'] and e.field == field['title']) for field in snapshot['artifact']['fields']}]}
               for s in snapshot['documents']]
    return case, snapshot, cases, results


@pytest.mark.parametrize('value', ['$1,250,000', 'USD 1250000.00', '1,250,000 USD', '1250000', '1250000.0'])
def test_exact_currency_formats_compare_without_approximation(value):
    assert canonical(value, 'usd_amount') == canonical('1250000', 'usd_amount')


@pytest.mark.parametrize('value', ['USD 1,25,000', '1250000 or 304000', '1.25 million', '$-1250000', True, {}, '', '1250000.001'])
def test_ambiguous_or_unbounded_amounts_do_not_become_supported_values(value):
    assert canonical(value, 'usd_amount')[0] == 'unrecognized'


def test_names_do_not_pass_by_substring_or_extra_people():
    assert canonical('Sarah Chen', 'person_name') == canonical('Dr. Sarah Chen', 'person_name')
    assert canonical('Dr. Sarah Chen and Dr. Michael Torres', 'person_name') != canonical('Dr. Sarah Chen', 'person_name')


def test_all_six_comparisons_include_the_optional_absence_without_credit():
    case, snapshot, cases, results = fixture()
    checked = check_suite(case, snapshot, cases, results)
    assert checked['complete'] and checked['source_supported']
    assert not checked['observed_semantic_failure']
    assert checked['credit_awarded'] is checked['module_completion_eligible'] is False
    assert checked['cases'][1]['fields'][2]['status'] == 'supported'


def test_agreement_with_wrong_learner_expectation_cannot_override_original_source():
    case, snapshot, cases, results = fixture()
    cases[0]['expectations'][1]['expected_value'] = '177000'
    results[0]['entities'][0][snapshot['artifact']['fields'][1]['searchphrase']] = '177000'
    checked = check_suite(case, snapshot, cases, results)
    field = checked['cases'][0]['fields'][1]
    assert field['matches_learner_expectation'] is True
    assert field['matches_source'] is field['expected_source_supported'] is False
    assert checked['source_supported'] is False and checked['observed_semantic_failure'] is True


@pytest.mark.parametrize('change', ['missing_key', 'empty_text', 'technical_failure', 'no_record', 'multiple_records'])
def test_unavailable_evidence_is_not_a_source_mismatch_or_demonstrated_pass(change):
    case, snapshot, cases, results = fixture()
    key = snapshot['artifact']['fields'][2]['searchphrase']
    if change == 'missing_key':
        del results[1]['entities'][0][key]
    elif change == 'empty_text':
        results[1]['entities'][0][key] = ''
    elif change == 'technical_failure':
        results[1]['status'] = 'unavailable'
    elif change == 'no_record':
        results[1]['entities'] = []
    else:
        results[1]['entities'].append(deepcopy(results[1]['entities'][0]))
    checked = check_suite(case, snapshot, cases, results)
    assert not checked['complete'] and not checked['source_supported'] and not checked['observed_semantic_failure']


def test_fabricated_optional_name_is_a_real_failure_even_if_quality_metrics_skip_it():
    case, snapshot, cases, results = fixture()
    results[1]['entities'][0][snapshot['artifact']['fields'][2]['searchphrase']] = 'Dr. Lisa Yamamoto'
    checked = check_suite(case, snapshot, cases, results)
    assert checked['complete'] and checked['observed_semantic_failure'] and not checked['source_supported']


@pytest.mark.parametrize('change', ['source_id', 'source_hash', 'artifact_hash', 'case_removed', 'case_duplicated', 'field_removed'])
def test_rejects_unbound_or_incomplete_case_inventory(change):
    case, snapshot, cases, results = fixture()
    if change == 'source_id':
        results[0]['source_id'] = 'foreign'
    elif change == 'source_hash':
        results[0]['source_sha256'] = '0' * 64
    elif change == 'artifact_hash':
        results[0]['artifact_sha256'] = '0' * 64
    elif change == 'case_removed':
        results.pop()
    elif change == 'case_duplicated':
        results[1] = deepcopy(results[0])
    else:
        cases[0]['expectations'].pop()
    with pytest.raises(CourseCatalogError):
        check_suite(case, snapshot, cases, results)


def repaired():
    case, original, cases, before = fixture()
    corrected = deepcopy(original)
    corrected['artifact']['fields'][1]['searchphrase'] += ' Use the entire project, not Year 1.'
    corrected['artifact_sha256'] = 'b' * 64
    after = deepcopy(before)
    old_key, new_key = original['artifact']['fields'][1]['searchphrase'], corrected['artifact']['fields'][1]['searchphrase']
    for result in after:
        result['artifact_sha256'] = corrected['artifact_sha256']
        result['entities'][0][new_key] = result['entities'][0].pop(old_key)
    before[0]['entities'][0][old_key] = '177000'
    return case, original, corrected, cases, before, after


def test_actual_failure_and_complete_unchanged_suite_support_only_mechanical_repair():
    case, original, corrected, cases, before, after = repaired()
    checked = check_repair(case, original, corrected, cases, cases, before, after)
    assert checked['repair_requirements_supported'] is True
    assert checked['changed_fields'] == ['Total Project Budget']
    assert checked['learner_explanation_requires_review'] is True and checked['credit_awarded'] is False


@pytest.mark.parametrize('change', ['different_artifact', 'same_revision', 'title_only', 'replaced_field', 'changed_answer', 'removed_case'])
def test_changed_identity_or_suite_cannot_claim_repair(change):
    case, original, corrected, cases, before, after = repaired()
    next_cases = deepcopy(cases)
    if change == 'different_artifact':
        corrected['artifact_id'] = 'other-extraction'
    elif change == 'same_revision':
        corrected['artifact_sha256'] = original['artifact_sha256']
    elif change == 'title_only':
        corrected['artifact']['fields'] = deepcopy(original['artifact']['fields'])
    elif change == 'replaced_field':
        corrected['artifact']['fields'][1]['id'] = 'new-field'
    elif change == 'changed_answer':
        next_cases[0]['expectations'][1]['expected_value'] = '177000'
    else:
        next_cases.pop()
    with pytest.raises(CourseCatalogError):
        check_repair(case, original, corrected, cases, next_cases, before, after)


@pytest.mark.parametrize('change', ['original_passed', 'original_technical_failure', 'corrected_failed', 'regression_failed', 'corrected_missing'])
def test_no_observed_failure_or_incomplete_regression_cannot_support_repair(change):
    case, original, corrected, cases, before, after = repaired()
    old_key = original['artifact']['fields'][1]['searchphrase']
    new_key = corrected['artifact']['fields'][1]['searchphrase']
    if change == 'original_passed':
        before[0]['entities'][0][old_key] = '485000'
    elif change == 'original_technical_failure':
        before[0]['status'] = 'unavailable'
    elif change == 'corrected_failed':
        after[0]['entities'][0][new_key] = '177000'
    elif change == 'regression_failed':
        after[1]['entities'][0][new_key] = '304000'
    else:
        del after[1]['entities'][0][corrected['artifact']['fields'][2]['searchphrase']]
    checked = check_repair(case, original, corrected, cases, cases, before, after)
    assert checked['repair_requirements_supported'] is False and checked['credit_awarded'] is False
