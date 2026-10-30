"""An authored calculation key cannot become a receipt or relax source checks."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from pydantic import ValidationError

from app.services.certification_versions.advanced_case import AdvancedNodesCase, load_advanced_case
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'advanced-nodes-case.json').read_text())


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


def test_exact_source_arithmetic_and_private_guidance_are_bound_without_release_credit(design):
    case = AdvancedNodesCase.model_validate(design)
    case.verify_contract(contract())
    case.verify_exercise(json.loads((DRAFT / 'advanced-nodes-exercise.json').read_text()))
    source = (DRAFT / 'documents' / case.source_filename).read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        case.verify_source(source, [p.get_text() for p in pdf])
    assert [c.expected_value for c in case.calculations] == ['45000.00', '517424.00', '542800.00']
    public = case.public_definition()
    assert not {'amounts', 'calculations', 'source_issues', 'review_guidance'} & public.keys()
    assert public['case_sha256'] == case.digest
    assert public['provenance'] == 'authored_budget_method_case_not_execution'
    assert all(o.assessment_status == 'implemented' for m in contract().modules
               if m.module_id == 'advanced_nodes' for o in m.outcomes)


@pytest.mark.parametrize('change', ['wrong_sum', 'duplicate_operand', 'omit_category', 'duplicate_calculation',
    'duplicate_amount', 'nonfinite', 'exponent', 'numeric_coercion', 'negative_amount', 'too_large',
    'expression_execution', 'model_only', 'required_code', 'fake_receipt', 'staff_queue', 'external_action',
    'duplicate_question', 'wrong_phase', 'wrong_outcome', 'duplicate_guide', 'duplicate_issue'])
def test_rejects_ambiguous_calculations_or_evidence_shortcuts(design, change):
    if change == 'wrong_sum':
        design['calculations'][0]['expected_value'] = '45001.00'
    elif change == 'duplicate_operand':
        design['calculations'][0]['inputs'][1] = 'weather_station'
    elif change == 'omit_category':
        design['calculations'][1]['inputs'].pop()
    elif change == 'duplicate_calculation':
        design['calculations'][1] = deepcopy(design['calculations'][0])
    elif change == 'duplicate_amount':
        design['amounts'][1] = deepcopy(design['amounts'][0])
    elif change in ('nonfinite', 'exponent', 'numeric_coercion', 'negative_amount', 'too_large'):
        design['amounts'][0]['value'] = {'nonfinite': 'NaN', 'exponent': '1.8e4', 'numeric_coercion': 18000,
                                       'negative_amount': '-18000.00', 'too_large': '1000000000.00'}[change]
    elif change == 'expression_execution':
        design['calculations'][0]['operation'] = 'eval'
    elif change == 'model_only':
        design['arithmetic_rule'] = 'accept_model_assurance'
    elif change == 'required_code':
        design['calculation_methods'] = ['restricted_code_node']
    elif change == 'fake_receipt':
        design['execution_receipt'] = {'status': 'completed'}
    elif change == 'staff_queue':
        design['assessment_policy'] = 'staff_must_approve'
    elif change == 'external_action':
        design['scope_policy'] = 'send_approved_budget'
    elif change == 'duplicate_question':
        design['questions'][1] = deepcopy(design['questions'][0])
    elif change == 'wrong_phase':
        design['questions'][0]['phase'] = 'after_execution'
    elif change == 'wrong_outcome':
        design['questions'][0]['outcome_id'] = 'advanced_nodes.parallel_safety'
    elif change == 'duplicate_guide':
        design['review_guidance'][1] = deepcopy(design['review_guidance'][0])
    else:
        design['source_issues'][1] = deepcopy(design['source_issues'][0])
    with pytest.raises(ValidationError):
        AdvancedNodesCase.model_validate(design)


@pytest.mark.parametrize('change', ['bytes', 'quote', 'page', 'coherent_wrong_amount'])
def test_rejects_wrong_source_even_when_arithmetic_is_internally_consistent(design, change):
    source = (DRAFT / 'documents/budget-justification.pdf').read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        texts = [p.get_text() for p in pdf]
    if change == 'bytes':
        source += b'changed'
    elif change == 'quote':
        design['source_issues'][0]['anchors'][0]['quote'] = 'Invented source text.'
    elif change == 'page':
        design['amounts'][0]['anchor']['page'] = 99
    else:
        design['amounts'][0]['value'] = '19000.00'
        design['calculations'][0]['expected_value'] = '46000.00'
    with pytest.raises(ValueError):
        AdvancedNodesCase.model_validate(design).verify_source(source, texts)


@pytest.mark.parametrize('change', ['method', 'evidence', 'passing', 'critical', 'missing_outcome'])
def test_case_cannot_weaken_the_declared_rubric(design, change):
    data = contract().model_dump(mode='json')
    module = next(m for m in data['modules'] if m['module_id'] == 'advanced_nodes')
    outcome = module['outcomes'][0]
    if change == 'method':
        outcome['method'] = 'deterministic'
    elif change == 'evidence':
        outcome['evidence'] = ['learner_decision']
    elif change == 'passing':
        outcome['passing_conditions'] = ['Any nonempty answer is enough.']
    elif change == 'critical':
        outcome['critical_failures'] = ['Only an empty answer fails.']
    else:
        module['outcomes'].pop()
    with pytest.raises(ValueError):
        AdvancedNodesCase.model_validate(design).verify_contract(OutcomeContract.model_validate(data))


@pytest.mark.parametrize('change', ['source', 'case_digest', 'count_credit', 'instructions', 'method'])
def test_exercise_binding_rejects_legacy_shortcuts(design, change):
    exercise = json.loads((DRAFT / 'advanced-nodes-exercise.json').read_text())
    if change == 'source':
        exercise['documents'] = ['other.pdf']
    elif change == 'case_digest':
        exercise['advanced_case_sha256'] = '0' * 64
    elif change == 'instructions':
        exercise['instructions'] = ['Enable an external API task before completing the exercise.']
    elif change == 'count_credit':
        exercise['star_criteria'] = {'one': 'Create three tasks.'}
    else:
        exercise['assessment_method'] = 'count_nodes'
    with pytest.raises(ValueError):
        AdvancedNodesCase.model_validate(design).verify_exercise(exercise)


def test_packaged_case_checks_course_source_binding(design, monkeypatch):
    from app.services.certification_versions import outcomes
    monkeypatch.setattr(outcomes, 'package_outcomes', lambda _: contract())
    exercise = json.loads((DRAFT / 'advanced-nodes-exercise.json').read_text())
    assets = {'advanced-cases/advanced_nodes.json': design, 'exercises.json': {'advanced_nodes': exercise}}
    package = SimpleNamespace(json=lambda name: deepcopy(assets[name]), manifest=SimpleNamespace(artifacts={
        'advanced-cases/advanced_nodes.json': 'a' * 64, 'documents/budget-justification.pdf': design['source_sha256']}))
    assert load_advanced_case(package).digest == AdvancedNodesCase.model_validate(design).digest
    package.manifest.artifacts['documents/budget-justification.pdf'] = 'b' * 64
    with pytest.raises(CourseCatalogError, match='invalid'):
        load_advanced_case(package)


@pytest.mark.parametrize('change', [None, 'missing_case', 'unknown_case', 'wrong_source', 'wrong_exercise'])
def test_catalog_validates_complete_draft_package_without_mutating_legacy(tmp_path, change):
    import hashlib
    import shutil
    from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog
    version = 'legacy-2026-10-02.1'
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    folder = tmp_path / 'courses' / version
    design = contract().model_dump(mode='json')
    # Local test package only; preserve the existing rubric to exercise catalog checks.
    design['rubric_id'] = 'legacy-2026-10-02'
    (folder / 'outcomes.json').write_text(json.dumps(design))
    exercise_path = folder / 'exercises.json'
    exercises = json.loads(exercise_path.read_text())
    exercises['advanced_nodes'] = json.loads((DRAFT / 'advanced-nodes-exercise.json').read_text())
    if change == 'wrong_exercise':
        exercises['advanced_nodes']['advanced_case_sha256'] = '0' * 64
    exercise_path.write_text(json.dumps(exercises))
    if change != 'wrong_source':
        shutil.copyfile(DRAFT / 'documents/budget-justification.pdf', folder / 'documents/budget-justification.pdf')
    if change != 'missing_case':
        (folder / 'advanced-cases').mkdir()
        shutil.copyfile(DRAFT / 'advanced-nodes-case.json', folder / 'advanced-cases' /
                        ('unknown.json' if change == 'unknown_case' else 'advanced_nodes.json'))
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
        assert load_advanced_case(catalog.load(version, preview=True)).source_sha256 == manifest['artifacts']['documents/budget-justification.pdf']
    else:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
