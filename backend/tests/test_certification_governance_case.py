"""Governance source/task identity cannot substitute for actual learner supervision."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import fitz
import pytest

from app.services.certification_versions.governance_case import GovernanceCase, load_governance_case
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'governance-capstone-case.json').read_text())


def test_complete_two_source_capstone_preserves_private_answers_and_separate_authenticated_decision_phases(design):
    case = GovernanceCase.model_validate(design)
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    case.verify_contract(contract)
    case.verify_exercise(json.loads((DRAFT / 'governance-exercise.json').read_text()))
    for source in case.sources:
        data = (DRAFT / 'documents' / source.filename).read_bytes()
        with fitz.open(stream=data, filetype='pdf') as pdf:
            case.verify_source(source.id, data, [p.get_text() for p in pdf])
    public = case.public_definition()
    assert 'expectations' not in public and 'review_guidance' not in public
    assert public['case_sha256'] == case.digest
    assert len(case.expectations) == 6 and len({q.phase for q in case.questions}) == 4
    assert all(o.assessment_status == 'implemented' for m in contract.modules if m.module_id == 'governance' for o in m.outcomes if o.method == 'structured_review')


@pytest.mark.parametrize('change', ['duplicate_source', 'source_filename', 'source_order', 'duplicate_field', 'comparison',
    'duplicate_expectation', 'empty_expectation', 'missing_expectation', 'duplicate_question', 'wrong_phase',
    'duplicate_guidance', 'invented_receipt', 'scope_expansion', 'retry_all', 'wrong_date', 'unissued_source', 'fake_grade'])
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
        design['fields'][3]['comparison'] = 'exact_text'
    elif change == 'duplicate_expectation':
        design['expectations'][1] = deepcopy(design['expectations'][0])
    elif change == 'empty_expectation':
        design['expectations'][0]['expected_value'] = ''
    elif change == 'missing_expectation':
        design['expectations'].pop()
    elif change == 'duplicate_question':
        design['questions'][1] = deepcopy(design['questions'][0])
    elif change == 'wrong_phase':
        design['questions'][1]['phase'] = 'before_original_execution'
    elif change == 'duplicate_guidance':
        design['review_guidance'][1] = deepcopy(design['review_guidance'][0])
    elif change == 'invented_receipt':
        design['provenance'] = 'actual_completed_batch'
    elif change == 'scope_expansion':
        design['scope_rule'] = 'share_everywhere'
    elif change == 'retry_all':
        design['delivery_rule'] = 'rerun_extraction_and_send_again'
    elif change == 'wrong_date':
        design['task_as_of'] = '2026-10-01'
    elif change == 'unissued_source':
        design['expectations'][3]['anchors'][0]['source_id'] = 'award'
    else:
        design['grade'] = 'pass'
    with pytest.raises(ValueError):
        GovernanceCase.model_validate(design)


@pytest.mark.parametrize('change', ['source_bytes', 'anchor', 'wrong_value', 'exercise_digest', 'count_award', 'rubric_evidence', 'coverage_method'])
def test_original_sources_exercise_and_source_bound_supervision_cannot_be_substituted(design, change):
    data = (DRAFT / 'documents/capstone-award-notice.pdf').read_bytes()
    with fitz.open(stream=data, filetype='pdf') as pdf:
        pages = [p.get_text() for p in pdf]
    exercise = json.loads((DRAFT / 'governance-exercise.json').read_text())
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    outcome = next(m for m in contract['modules'] if m['module_id'] == 'governance')['outcomes'][0]
    if change == 'source_bytes':
        data += b'changed'
    elif change == 'anchor':
        design['expectations'][0]['anchors'][0]['quote'] = 'An invented original source passage'
    elif change == 'wrong_value':
        design['expectations'][2]['expected_value'] = '999999'
    elif change == 'exercise_digest':
        exercise['governance_case_sha256'] = '0' * 64
    elif change == 'count_award':
        exercise['star_criteria'] = {'1': 'Three documents'}
    elif change == 'rubric_evidence':
        outcome['evidence'] = ['learner_decision']
    else:
        outcome['method'] = 'deterministic'
    case = GovernanceCase.model_validate(design)
    with pytest.raises(ValueError):
        case.verify_source('award', data, pages)
        case.verify_exercise(exercise)
        case.verify_contract(OutcomeContract.model_validate(contract))


@pytest.mark.parametrize('change', [None, 'missing_case', 'unknown_case', 'wrong_source', 'wrong_exercise'])
def test_catalog_requires_bound_case_and_every_original_source(tmp_path, change):
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    version = 'legacy-2026-10-02.1'
    folder = tmp_path / 'courses' / version
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    contract['rubric_id'] = 'legacy-2026-10-02'
    (folder / 'outcomes.json').write_text(json.dumps(contract))
    exercises = json.loads((folder / 'exercises.json').read_text())
    exercises['governance'] = json.loads((DRAFT / 'governance-exercise.json').read_text())
    if change == 'wrong_exercise':
        exercises['governance']['governance_case_sha256'] = '0' * 64
    (folder / 'exercises.json').write_text(json.dumps(exercises))
    if change != 'wrong_source':
        for name in exercises['governance']['documents']:
            shutil.copyfile(DRAFT / 'documents' / name, folder / 'documents' / name)
    if change != 'missing_case':
        (folder / 'governance-cases').mkdir()
        shutil.copyfile(DRAFT / 'governance-capstone-case.json', folder / 'governance-cases' /
                        ('unknown.json' if change == 'unknown_case' else 'governance.json'))
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
        assert len(load_governance_case(catalog.load(version, preview=True)).sources) == 2
    else:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
