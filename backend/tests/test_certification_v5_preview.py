"""Complete preview assembly remains reproducible, isolated and non-enrollable."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from app.services.certification_versions.authoring import choose_default, publish
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('certification_v5_preview', ROOT / 'scripts/assemble_certification_v5_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
VERSION = 'v5.0-isolated-test.1'


def test_full_preview_uses_every_new_lesson_and_assessment_without_touching_application_catalog(tmp_path):
    registry = (CATALOG_ROOT / 'registry.json').read_bytes()
    output = preview.assemble(tmp_path / 'first', VERSION)
    preview.assemble(tmp_path / 'second', VERSION)
    package = CourseCatalog(output).load(VERSION, preview=True)
    second = CourseCatalog(tmp_path / 'second').load(VERSION, preview=True)
    assert package.manifest_bytes == second.manifest_bytes
    assert package.artifact_bytes == second.artifact_bytes
    public = json.loads((output / 'public-course.json').read_text())
    report = json.loads((output / 'preview-report.json').read_text())
    assert public['prerequisites'] == {module.id: list(module.prerequisites) for module in package.manifest.modules}
    assert public['levels'] == package.json('course-structure.json')['levels']
    assert public['tiers'] == package.json('course-structure.json')['tiers']
    assert public['progression_policy']['required_outcomes'] == 33
    assert public['progression_policy']['required_modules'] == 11
    assert public['progression_policy']['base_xp_total'] == 1850
    assert public['progression_policy']['state'] == 'design_draft'
    assert report['progression_policy_id'] == 'required-outcomes-flexible-order.1'
    assert 'progression-policy.json' in package.manifest.artifacts
    assert (report['modules'], report['lessons'], report['required_outcomes']) == (11, 74, 33)
    assert report['release_verified_outcomes'] == 0
    for key in ('grading_available', 'enrollment_available', 'application_registry_changed', 'credit_policy_finalized', 'progression_policy_finalized'):
        assert report[key] is False
    expected = {'ai_literacy': 'scenarioAssessment', 'foundations': 'practicalPreparation',
                'process_mapping': 'processAssessment', 'workflow_design': 'workflowDesignAssessment',
                'extraction_engine': 'repairAssignment', 'multi_step': 'connectedWorkflowAssessment',
                'advanced_nodes': 'budgetWorkflowAssessment', 'output_delivery': 'outputWorkflowAssessment',
                'validation_qa': 'validationAssessment', 'batch_processing': 'batchAssessment',
                'governance': 'governanceAssessment'}
    for module in public['modules']:
        assert module[expected[module['id']]]
        assert module['assessment'] is None
        authored = json.loads((preview.DATA / f'drafts/v5.0/{module["id"].replace("_", "-")}-teaching.json').read_text())
        assert module['description'] == authored['module_patch']['description']
        assert [(lesson['id'], lesson['revision'], lesson['content']) for lesson in module['lessons']] == [
            (lesson['id'], lesson['revision'], lesson['content']) for lesson in authored['replacements']]
        exercise = package.json('exercises.json')[module['id']]
        assert exercise['expected_values'] == exercise['star_criteria'] == {}
    for module in ('validation_qa', 'governance'):
        assert next(item for item in public['modules'] if item['id'] == module)['scenarioAssessment']
    serialized = json.dumps(public)
    assert 'correct_choice_id' not in serialized and 'review_guidance' not in serialized
    for new_enrollment in (False, True):
        with pytest.raises(CourseCatalogError, match='Draft'):
            CourseCatalog(output).load(VERSION, new_enrollment=new_enrollment)
    with pytest.raises(CourseCatalogError):
        choose_default(CourseCatalog(output), VERSION)
    before = (output / 'registry.json').read_bytes()
    with pytest.raises(CourseCatalogError):
        publish(CourseCatalog(output), VERSION, expected_digest=package.manifest_sha256)
    assert (output / 'registry.json').read_bytes() == before
    assert (CATALOG_ROOT / 'registry.json').read_bytes() == registry
    assert set(json.loads(before)) == {'schema_version', 'releases'}
    with pytest.raises(ValueError, match='new output'):
        preview.assemble(output, VERSION)


@pytest.mark.parametrize('location', [CATALOG_ROOT, CATALOG_ROOT / 'unapproved-preview'])
def test_preview_cannot_write_to_application_registry(location):
    with pytest.raises(ValueError, match='outside'):
        preview.assemble(location, VERSION)


@pytest.mark.parametrize('problem', ['missing_case', 'mismatched_case', 'stale_lesson', 'legacy_scoring'])
def test_incomplete_or_contradictory_preview_leaves_no_partial_output(tmp_path, problem):
    data = tmp_path / 'data'
    data.mkdir()
    for name in ('lessons.json', 'panel-modules.json', 'course-structure.json'):
        shutil.copyfile(preview.DATA / name, data / name)
    shutil.copytree(preview.DATA / 'documents', data / 'documents')
    shutil.copytree(preview.DATA / 'drafts', data / 'drafts')
    draft = data / 'drafts/v5.0'
    if problem == 'missing_case':
        (draft / 'governance-capstone-case.json').unlink()
    elif problem == 'stale_lesson':
        path = draft / 'foundations-teaching.json'
        value = json.loads(path.read_text())
        value['replacements'][0]['revision'] = 1
        path.write_text(json.dumps(value))
    else:
        path = draft / 'foundations-exercise.json'
        value = json.loads(path.read_text())
        if problem == 'legacy_scoring':
            value['star_criteria'] = {'1': 'Three fields earn credit'}
        else:
            value['scope_proposal_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
    with pytest.raises((ValueError, FileNotFoundError)):
        preview.assemble(tmp_path / 'output', VERSION, data_root=data)
    assert not (tmp_path / 'output').exists()
    assert not list(tmp_path.glob('.certification-preview-*'))
