"""The new Foundations assignment must match its saved-scope assessment."""
import json
import hashlib
from pathlib import Path
import shutil

import pytest

from app.services.certification_versions.scope_proposal import ScopeProposalCase
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.delivery import public_modules

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


def assets():
    return (ScopeProposalCase.model_validate_json((DRAFT / 'foundations-proposal.json').read_bytes()),
            json.loads((DRAFT / 'foundations-exercise.json').read_text()))


def test_draft_exercise_requires_every_saved_value_check_without_legacy_scoring():
    case, exercise = assets()
    case.verify_exercise(exercise)
    prompts = json.loads((DRAFT / 'foundations-decisions.json').read_text())
    values = next(prompt for prompt in prompts if prompt['id'] == 'value_review')
    assert exercise['expected_fields'] == values['required_fields']
    assert exercise['documents'] != [case.original_source_filename]
    assert exercise['chat_instructions'][1:] == exercise['instructions']


@pytest.mark.parametrize('change', ['method', 'case', 'revision', 'source', 'field', 'answer_key', 'stars', 'instructions', 'chat', 'overview', 'malformed'])
def test_mismatched_or_legacy_assignment_cannot_bind_new_scoped_assessment(change):
    case, exercise = assets()
    if change == 'method':
        exercise['assessment_method'] = 'field_count'
    elif change == 'case':
        exercise['assessment_case_id'] = 'another-case'
    elif change == 'revision':
        exercise['scope_proposal_sha256'] = '0' * 64
    elif change == 'source':
        exercise['documents'] = [case.original_source_filename]
    elif change == 'field':
        exercise['expected_fields'].pop()
    elif change == 'answer_key':
        exercise['expected_values'] = {'PI Name': ['answer exposed in exercise']}
    elif change == 'stars':
        exercise['star_criteria'] = {'1': 'Three fields are enough'}
    elif change == 'instructions':
        exercise['instructions'] = []
    elif change == 'chat':
        exercise['chat_instructions'] = [' ']
    elif change == 'overview':
        exercise['overview'] = ''
    else:
        exercise = []
    with pytest.raises(ValueError, match='Foundations exercise'):
        case.verify_exercise(exercise)


@pytest.mark.parametrize('change', [None, 'missing_proposal', 'wrong_case_digest'])
def test_catalog_binds_new_assignment_before_exposing_preparation(tmp_path, change):
    root = tmp_path / 'courses'
    shutil.copytree(CATALOG_ROOT, root)
    version = 'legacy-2026-10-02.1'
    directory = root / version
    manifest = json.loads((directory / 'manifest.json').read_text())
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    manifest['rubric_id'] = contract['rubric_id']
    paths = {'outcomes.json': 'outcomes.json', 'decisions/foundations.json': 'foundations-decisions.json'}
    if change != 'missing_proposal':
        paths['proposals/foundations.json'] = 'foundations-proposal.json'
    for target, source in paths.items():
        (directory / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DRAFT / source, directory / target)
        manifest['artifacts'][target] = hashlib.sha256((directory / target).read_bytes()).hexdigest()
    exercises = json.loads((directory / 'exercises.json').read_text())
    exercises['foundations'] = assets()[1]
    if change == 'wrong_case_digest':
        exercises['foundations']['scope_proposal_sha256'] = '0' * 64
    (directory / 'exercises.json').write_text(json.dumps(exercises))
    manifest['artifacts']['exercises.json'] = hashlib.sha256((directory / 'exercises.json').read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    registry = json.loads((root / 'registry.json').read_text())
    registry['releases'][version]['manifest_sha256'] = hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()
    (root / 'registry.json').write_text(json.dumps(registry))
    catalog = CourseCatalog(root)
    if change:
        with pytest.raises(CourseCatalogError):
            catalog.load(version, preview=True)
    else:
        package = catalog.load(version, preview=True)
        assert next(module for module in public_modules(package) if module['id'] == 'foundations')['practicalPreparation'] is True
        assert package.json('exercises.json')['foundations'] == assets()[1]
        with pytest.raises(CourseCatalogError, match='Draft'):
            catalog.load(version)
