"""Authored file/handoff assignment cannot substitute for actual learner work."""
from copy import deepcopy
import json
from pathlib import Path

import fitz
import pytest
from pydantic import ValidationError

from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.output_case import OutputDeliveryCase, load_output_case
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


@pytest.fixture
def design():
    return json.loads((DRAFT / 'output-delivery-case.json').read_text())


def test_source_guidance_periods_and_explicit_rehearsal_are_bound_without_delivery(design):
    case = OutputDeliveryCase.model_validate(design)
    case.verify_contract(contract())
    case.verify_exercise(json.loads((DRAFT / 'output-delivery-exercise.json').read_text()))
    source = (DRAFT / 'documents' / case.source_filename).read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        case.verify_source(source, [p.get_text() for p in pdf])
    public = case.public_definition()
    assert 'source_checks' not in public and 'review_guidance' not in public
    assert public['case_sha256'] == case.digest
    assert public['destination']['audience'] == 'enrolled_learner_only'
    assert public['destination']['first_attempt'] == 'controlled_rejection_before_destination_write'
    assert {a.file_type for a in case.artifacts} == {'pdf', 'csv'}
    assert all(o.assessment_status == 'implemented' for m in contract().modules
               if m.module_id == 'output_delivery' for o in m.outcomes)


@pytest.mark.parametrize('change', ['actual_receipt', 'duplicate_question', 'wrong_phase', 'wrong_outcome',
    'duplicate_guide', 'missing_artifact', 'wrong_format', 'duplicate_artifact', 'omit_period', 'merge_periods',
    'external_destination', 'shared_audience', 'broader_scope', 'unannounced_failure', 'rerun_generation',
    'package_builder', 'node_count_credit', 'reuse_approval', 'claim_delivery', 'staff_queue', 'duplicate_check', 'unknown_field', 'omit_check', 'wrong_check_field'])
def test_rejects_evidence_authority_and_assessment_shortcuts(design, change):
    if change == 'actual_receipt':
        design['provenance'] = 'actual_delivery_receipt'
    elif change == 'duplicate_question':
        design['questions'][1] = deepcopy(design['questions'][0])
    elif change == 'wrong_phase':
        design['questions'][1]['phase'] = 'after_delivery_attempt'
    elif change == 'wrong_outcome':
        design['questions'][1]['outcome_id'] = design['questions'][0]['outcome_id']
    elif change == 'duplicate_guide':
        design['review_guidance'][1] = deepcopy(design['review_guidance'][0])
    elif change == 'missing_artifact':
        design['artifacts'].pop()
    elif change == 'wrong_format':
        design['artifacts'][1]['file_type'] = 'pdf'
    elif change == 'duplicate_artifact':
        design['artifacts'][1] = deepcopy(design['artifacts'][0])
    elif change == 'omit_period':
        design['artifacts'][0]['required_fields'].remove('Reporting Period')
    elif change == 'merge_periods':
        design['artifacts'][1]['required_fields'].remove('Year 2 Budget Spent')
    elif change in ('external_destination', 'shared_audience', 'broader_scope', 'unannounced_failure', 'rerun_generation'):
        key, value = {'external_destination': ('id', 'external_email'), 'shared_audience': ('audience', 'all_staff'),
            'broader_scope': ('data_scope', 'entire_source_folder'), 'unannounced_failure': ('first_attempt', 'invent_failure_receipt'),
            'rerun_generation': ('recovery', 'rerun_all_steps')}[change]
        design['destination'][key] = value
    elif change in ('package_builder', 'node_count_credit', 'reuse_approval', 'claim_delivery', 'staff_queue'):
        key = {'package_builder': 'bundle_rule', 'node_count_credit': 'artifact_rule', 'reuse_approval': 'release_rule',
            'claim_delivery': 'delivery_rule', 'staff_queue': 'assessment_policy'}[change]
        design[key] = change
    elif change == 'duplicate_check':
        design['source_checks'][1] = deepcopy(design['source_checks'][0])
    elif change == 'unknown_field':
        design['source_checks'][0]['field'] = 'Invented Total'
    elif change == 'omit_check':
        design['source_checks'].pop()
    elif change == 'wrong_check_field':
        design['source_checks'][0]['field'] = 'Remaining Budget'
    with pytest.raises(ValidationError):
        OutputDeliveryCase.model_validate(design)


@pytest.mark.parametrize('change', ['source', 'quote', 'page', 'rubric', 'evidence', 'exercise_hash', 'count_credit'])
def test_rejects_changed_source_or_weakened_rubric(design, change):
    course = contract()
    exercise = json.loads((DRAFT / 'output-delivery-exercise.json').read_text())
    source = (DRAFT / 'documents/progress-report-year2.pdf').read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        pages = [p.get_text() for p in pdf]
    if change == 'source':
        source += b'changed'
    elif change == 'quote':
        design['source_checks'][0]['anchors'][0]['quote'] = 'A fabricated source fact that never appeared.'
    elif change == 'page':
        design['source_checks'][0]['anchors'][0]['page'] = 99
    elif change == 'rubric':
        design['review_guidance'][0]['passing_conditions'] = ['A file merely exists.']
    elif change == 'evidence':
        changed = course.model_dump(mode='json')
        next(m for m in changed['modules'] if m['module_id'] == 'output_delivery')['outcomes'][0]['evidence'] = ['learner_decision']
        course = OutcomeContract.model_validate(changed)
    elif change == 'exercise_hash':
        exercise['output_case_sha256'] = '0' * 64
    elif change == 'count_credit':
        exercise['star_criteria'] = {'1': 'Two output nodes exist.'}
    case = OutputDeliveryCase.model_validate(design)
    with pytest.raises(ValueError):
        case.verify_contract(course)
        case.verify_source(source, pages)
        case.verify_exercise(exercise)


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
    exercises['output_delivery'] = json.loads((DRAFT / 'output-delivery-exercise.json').read_text())
    if change == 'wrong_exercise':
        exercises['output_delivery']['output_case_sha256'] = '0' * 64
    exercise_path.write_text(json.dumps(exercises))
    if change != 'wrong_source':
        shutil.copyfile(DRAFT / 'documents/progress-report-year2.pdf', folder / 'documents/progress-report-year2.pdf')
    if change != 'missing_case':
        (folder / 'output-cases').mkdir()
        shutil.copyfile(DRAFT / 'output-delivery-case.json', folder / 'output-cases' /
                        ('unknown.json' if change == 'unknown_case' else 'output_delivery.json'))
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
        assert load_output_case(catalog.load(version, preview=True)).source_sha256 == manifest['artifacts']['documents/progress-report-year2.pdf']
    else:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
