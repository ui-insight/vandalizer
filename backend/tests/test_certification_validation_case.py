"""An authored suite is neither an observed failure nor a completed retest."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

import fitz
import pytest

from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.validation_case import ValidationCase, load_validation_case

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'validation-qa-case.json').read_text())


def test_complete_sources_have_anchored_expectations_without_public_answer_keys(design):
    case = ValidationCase.model_validate(design)
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    case.verify_contract(contract)
    case.verify_exercise(json.loads((DRAFT / 'validation-qa-exercise.json').read_text()))
    for source in case.sources:
        data = (DRAFT / 'documents' / source.filename).read_bytes()
        with fitz.open(stream=data, filetype='pdf') as pdf:
            case.verify_source(source.id, data, [p.get_text() for p in pdf])
    public = case.public_definition()
    assert 'expectations' not in public and 'review_guidance' not in public
    assert public['case_sha256'] == case.digest
    assert sum(e.expected_value is None for e in case.expectations) == 1
    assert all(o.assessment_status == 'implemented' for m in contract.modules
               if m.module_id == 'validation_qa' for o in m.outcomes if o.method == 'structured_review')


@pytest.mark.parametrize('change', ['duplicate_source', 'source_filename', 'duplicate_field', 'wrong_comparison',
    'duplicate_expectation', 'empty_expectation', 'missing_expectation', 'unreviewed_absence', 'wrong_absence',
    'duplicate_question', 'wrong_phase', 'wrong_outcome', 'duplicate_guidance', 'invented_receipt', 'count_credit',
    'technical_failure', 'optional_skip', 'delete_failure', 'extra_field'])
def test_rejects_shortcuts_that_remove_representative_coverage_or_actual_failure(design, change):
    if change == 'duplicate_source':
        design['sources'][1] = deepcopy(design['sources'][0])
    elif change == 'source_filename':
        design['sources'][0]['filename'] = design['sources'][1]['filename']
    elif change == 'duplicate_field':
        design['fields'][1] = deepcopy(design['fields'][0])
    elif change == 'wrong_comparison':
        design['fields'][1]['comparison'] = 'person_name'
    elif change == 'duplicate_expectation':
        design['expectations'][1] = deepcopy(design['expectations'][0])
    elif change == 'empty_expectation':
        design['expectations'][0]['expected_value'] = ''
    elif change == 'missing_expectation':
        design['expectations'].pop()
    elif change == 'unreviewed_absence':
        design['expectations'][-1]['absence_policy'] = 'required_source_value'
    elif change == 'wrong_absence':
        design['expectations'][0].update(expected_value=None, absence_policy='absent_when_role_not_explicitly_named')
    elif change == 'duplicate_question':
        design['questions'][1] = deepcopy(design['questions'][0])
    elif change == 'wrong_phase':
        design['questions'][1]['phase'] = 'before_original_run'
    elif change == 'wrong_outcome':
        design['questions'][0]['outcome_id'] = 'validation_qa.quality_meaning'
    elif change == 'duplicate_guidance':
        design['review_guidance'][1] = deepcopy(design['review_guidance'][0])
    elif change == 'invented_receipt':
        design['provenance'] = 'actual_failed_validation_run'
    elif change == 'count_credit':
        design['assessment_policy'] = 'pass_with_five_tests'
    elif change == 'technical_failure':
        design['failure_rule'] = 'provider_error_counts_as_observed_semantic_failure'
    elif change == 'optional_skip':
        design['absence_rule'] = 'skip_optional_fields'
    elif change == 'delete_failure':
        design['repair_rule'] = 'delete_failed_case_and_retest_subset'
    else:
        design['grade'] = 'pass'
    with pytest.raises(ValueError):
        ValidationCase.model_validate(design)


@pytest.mark.parametrize('change', ['source_bytes', 'anchor', 'expected_value', 'exercise_key', 'count_award', 'rubric_evidence'])
def test_source_exercise_and_rubric_bindings_cannot_be_replaced(design, change):
    data = (DRAFT / 'documents/nsf-proposal-alpine-ecology.pdf').read_bytes()
    with fitz.open(stream=data, filetype='pdf') as pdf:
        pages = [p.get_text() for p in pdf]
    exercise = json.loads((DRAFT / 'validation-qa-exercise.json').read_text())
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    if change == 'source_bytes':
        data += b'changed'
    elif change == 'anchor':
        design['expectations'][0]['anchors'][0]['quote'] = 'An invented original source passage'
    elif change == 'expected_value':
        design['expectations'][1]['expected_value'] = '177000'
        # Preserve a genuine annual figure elsewhere; the whole-project anchor
        # alone must not be accepted as support for that altered value.
        design['expectations'][1]['anchors'] = [design['expectations'][1]['anchors'][0]]
    elif change == 'exercise_key':
        exercise['validation_case_sha256'] = '0' * 64
    elif change == 'count_award':
        exercise['star_criteria'] = {'1': 'Five checks'}
    else:
        next(m for m in contract['modules'] if m['module_id'] == 'validation_qa')['outcomes'][1]['evidence'] = ['learner_decision']
    case = ValidationCase.model_validate(design)
    with pytest.raises(ValueError):
        case.verify_source('nsf', data, pages)
        case.verify_exercise(exercise)
        case.verify_contract(OutcomeContract.model_validate(contract))


def test_nsf_readable_draft_preserves_all_substantive_text_and_legacy_bytes():
    old = DRAFT.parents[1] / 'documents/nsf-proposal-alpine-ecology.pdf'
    assert hashlib.sha256(old.read_bytes()).hexdigest() == 'eed235f9fdcf7ae37a548dd34ca677a98d437ace2c1814da4ee37dafb9f33821'
    with fitz.open(old) as pdf:
        original = ' '.join(' '.join(p.get_text() for p in pdf).split())
    with fitz.open(DRAFT / 'documents/nsf-proposal-alpine-ecology.pdf') as pdf:
        assert len(pdf) == 1
        text = re.sub(r'Synthetic training document \| Unpublished 5.0 draft\s*Page 1', '', pdf[0].get_text())
        assert ' '.join(text.split()) == original
        assert any(font[1] == 'ttf' for font in pdf[0].get_fonts())


@pytest.mark.parametrize('change', [None, 'missing_case', 'unknown_case', 'wrong_source', 'wrong_exercise'])
def test_packaged_case_requires_both_original_sources_and_exact_exercise(tmp_path, change):
    version = 'legacy-2026-10-02.1'
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    folder = tmp_path / 'courses' / version
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    contract['rubric_id'] = 'legacy-2026-10-02'
    (folder / 'outcomes.json').write_text(json.dumps(contract))
    exercises = json.loads((folder / 'exercises.json').read_text())
    exercises['validation_qa'] = json.loads((DRAFT / 'validation-qa-exercise.json').read_text())
    if change == 'wrong_exercise':
        exercises['validation_qa']['validation_case_sha256'] = '0' * 64
    (folder / 'exercises.json').write_text(json.dumps(exercises))
    if change != 'wrong_source':
        for name in exercises['validation_qa']['documents']:
            shutil.copyfile(DRAFT / 'documents' / name, folder / 'documents' / name)
    if change != 'missing_case':
        (folder / 'validation-cases').mkdir()
        shutil.copyfile(DRAFT / 'validation-qa-case.json', folder / 'validation-cases' /
                        ('unknown.json' if change == 'unknown_case' else 'validation_qa.json'))
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['artifacts'] = {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in folder.rglob('*') if p.is_file() and p != manifest_path}
    manifest_path.write_text(json.dumps(manifest))
    registry_path = tmp_path / 'courses/registry.json'
    registry = json.loads(registry_path.read_text())
    registry['releases'][version]['manifest_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(registry))
    catalog = CourseCatalog(tmp_path / 'courses')
    if change is None:
        assert len(load_validation_case(catalog.load(version, preview=True)).sources) == 2
    else:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
