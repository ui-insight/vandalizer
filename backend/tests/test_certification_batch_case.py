"""Batch counts, pilot claims and authored recovery are not actual receipts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

import fitz
import pytest

from app.services.certification_versions.batch_case import BatchCase, load_batch_case
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'batch-processing-case.json').read_text())


def test_complete_three_source_case_preserves_private_answers_and_separate_approval_phases(design):
    case = BatchCase.model_validate(design)
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    case.verify_contract(contract)
    case.verify_exercise(json.loads((DRAFT / 'batch-processing-exercise.json').read_text()))
    for source in case.sources:
        data = (DRAFT / 'documents' / source.filename).read_bytes()
        with fitz.open(stream=data, filetype='pdf') as pdf:
            case.verify_source(source.id, data, [p.get_text() for p in pdf])
    public = case.public_definition()
    assert 'expectations' not in public and 'review_guidance' not in public
    assert public['case_sha256'] == case.digest
    assert len(case.expectations) == 15 and len({q.phase for q in case.questions}) == 4
    assert all(o.assessment_status == 'implemented' for m in contract.modules if m.module_id == 'batch_processing' for o in m.outcomes)


@pytest.mark.parametrize('change', ['duplicate_source', 'source_filename', 'source_order', 'duplicate_field', 'comparison',
    'duplicate_expectation', 'empty_expectation', 'missing_expectation', 'duplicate_question', 'wrong_phase',
    'duplicate_guidance', 'invented_receipt', 'count_credit', 'retry_all', 'wrong_pilot', 'fabricated_cost', 'fake_grade'])
def test_rejects_shortcuts_in_assignment_contract(design, change):
    if change == 'duplicate_source':
        design['sources'][1] = deepcopy(design['sources'][0])
    elif change == 'source_filename':
        design['sources'][0]['filename'] = design['sources'][1]['filename']
    elif change == 'source_order':
        design['sources'].reverse()
    elif change == 'duplicate_field':
        design['fields'][1] = deepcopy(design['fields'][0])
    elif change == 'comparison':
        design['fields'][2]['comparison'] = 'exact_text'
    elif change == 'duplicate_expectation':
        design['expectations'][1] = deepcopy(design['expectations'][0])
    elif change == 'empty_expectation':
        design['expectations'][0]['expected_value'] = ''
    elif change == 'missing_expectation':
        design['expectations'].pop()
    elif change == 'duplicate_question':
        design['questions'][1] = deepcopy(design['questions'][0])
    elif change == 'wrong_phase':
        design['questions'][1]['phase'] = 'before_pilot'
    elif change == 'duplicate_guidance':
        design['review_guidance'][1] = deepcopy(design['review_guidance'][0])
    elif change == 'invented_receipt':
        design['provenance'] = 'actual_completed_batch'
    elif change == 'count_credit':
        design['coverage_rule'] = 'three_completed_results'
    elif change == 'retry_all':
        design['recovery_rule'] = 'rerun_every_item'
    elif change == 'wrong_pilot':
        design['pilot_source_ids'] = ['proposal_1', 'proposal_1']
    elif change == 'fabricated_cost':
        design['resource_rule'] = 'estimate_price_as_measured'
    else:
        design['grade'] = 'pass'
    with pytest.raises(ValueError):
        BatchCase.model_validate(design)


@pytest.mark.parametrize('change', ['source_bytes', 'anchor', 'wrong_value', 'exercise_digest', 'count_award', 'rubric_evidence', 'coverage_method'])
def test_original_sources_exercise_and_deterministic_coverage_cannot_be_substituted(design, change):
    data = (DRAFT / 'documents/proposal-batch-1.pdf').read_bytes()
    with fitz.open(stream=data, filetype='pdf') as pdf:
        pages = [p.get_text() for p in pdf]
    exercise = json.loads((DRAFT / 'batch-processing-exercise.json').read_text())
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    outcome = next(m for m in contract['modules'] if m['module_id'] == 'batch_processing')['outcomes'][0]
    if change == 'source_bytes':
        data += b'changed'
    elif change == 'anchor':
        design['expectations'][0]['anchors'][0]['quote'] = 'An invented original source passage'
    elif change == 'wrong_value':
        design['expectations'][2]['expected_value'] = '999999'
    elif change == 'exercise_digest':
        exercise['batch_case_sha256'] = '0' * 64
    elif change == 'count_award':
        exercise['star_criteria'] = {'1': 'Three documents'}
    elif change == 'rubric_evidence':
        outcome['evidence'] = ['learner_decision']
    else:
        outcome['method'] = 'structured_review'
    case = BatchCase.model_validate(design)
    with pytest.raises(ValueError):
        case.verify_source('proposal_1', data, pages)
        case.verify_exercise(exercise)
        case.verify_contract(OutcomeContract.model_validate(contract))


@pytest.mark.parametrize('number,sha256', [(1, 'dc9725bac8f41ba4d233341cfa50a20ef2e3c0092316acbd5d9088e143bc31c0'),
    (2, '7a06e6bf6840983c1c9089b96b5fd50790b8f1bc62fb6a62d8b7a652f1792876'),
    (3, '2676b264fb236116658097efb99d8d114f7e1f8acb35abf751ec43f2e08cc5b9')])
def test_readable_draft_preserves_every_original_substantive_string_and_proposal_number(number, sha256):
    name = f'proposal-batch-{number}.pdf'
    old = DRAFT.parents[1] / 'documents' / name
    assert hashlib.sha256(old.read_bytes()).hexdigest() == sha256
    with fitz.open(old) as pdf:
        original = ' '.join(' '.join(page.get_text() for page in pdf).split())
    with fitz.open(DRAFT / 'documents' / name) as pdf:
        assert len(pdf) == 1
        text = ' '.join(page.get_text() for page in pdf)
    text = re.sub(r'Synthetic training document \| Unpublished 5\.0 draft\s*Page \d+', '', text)
    assert ' '.join(text.split()) == original


@pytest.mark.parametrize('change', [None, 'missing_case', 'unknown_case', 'wrong_source', 'wrong_exercise'])
def test_catalog_requires_bound_case_and_every_original_source(tmp_path, change):
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    version = 'legacy-2026-10-02.1'
    folder = tmp_path / 'courses' / version
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    contract['rubric_id'] = 'legacy-2026-10-02'
    (folder / 'outcomes.json').write_text(json.dumps(contract))
    exercises = json.loads((folder / 'exercises.json').read_text())
    exercises['batch_processing'] = json.loads((DRAFT / 'batch-processing-exercise.json').read_text())
    if change == 'wrong_exercise':
        exercises['batch_processing']['batch_case_sha256'] = '0' * 64
    (folder / 'exercises.json').write_text(json.dumps(exercises))
    if change != 'wrong_source':
        for name in exercises['batch_processing']['documents']:
            shutil.copyfile(DRAFT / 'documents' / name, folder / 'documents' / name)
    if change != 'missing_case':
        (folder / 'batch-cases').mkdir()
        shutil.copyfile(DRAFT / 'batch-processing-case.json', folder / 'batch-cases' /
                        ('unknown.json' if change == 'unknown_case' else 'batch_processing.json'))
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
        assert len(load_batch_case(catalog.load(version, preview=True)).sources) == 3
    else:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
