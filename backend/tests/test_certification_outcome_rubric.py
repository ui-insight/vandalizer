"""Synthetic release flags test runner boundaries; they are not calibration."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError
from app.services.certification_versions.grading import grade, load_rubric, pinned_progress
from app.services.certification_versions.module_readiness import ModuleReadiness
from app.services.certification_versions.outcomes import package_outcomes
from app.services.certification_versions.rubrics import competency_v5
from tests.test_certification_v5_preview import preview, VERSION

SELECTED = {'review_attempt_id': '1' * 32, 'scenario_attempt_id': '2' * 32}


@pytest.fixture
def candidate(tmp_path):
    root = preview.assemble(tmp_path / 'candidate', VERSION)
    folder = root / VERSION
    # Synthetic metadata only. Production drafts remain implemented/unverified.
    contract = json.loads((folder / 'outcomes.json').read_text())
    contract['state'] = 'release_candidate'
    for module in contract['modules']:
        for outcome in module['outcomes']:
            outcome['assessment_status'] = 'verified'
    (folder / 'outcomes.json').write_text(json.dumps(contract))
    policy = json.loads((folder / 'progression-policy.json').read_text())
    policy['state'] = 'release_candidate'  # Isolated synthetic review metadata only.
    (folder / 'progression-policy.json').write_text(json.dumps(policy))
    (folder / 'rubric.py').write_bytes(Path(competency_v5.__file__).read_bytes())
    def reload(changes=None):
        manifest = json.loads((folder / 'manifest.json').read_text())
        if changes:
            changes(manifest)
        for name in manifest['artifacts']:
            manifest['artifacts'][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        registry = json.loads((root / 'registry.json').read_text())
        registry['releases'][VERSION]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        (root / 'registry.json').write_text(json.dumps(registry))
        return CourseCatalog(root).load(VERSION, preview=True)
    return SimpleNamespace(folder=folder, reload=reload, package=reload(),
        progress=SimpleNamespace(user_id='learner', enrollment_id='owned-enrollment', course_version=VERSION, modules={}, total_xp=0))


def snapshot(candidate, selected=None, state='supported'):
    selected = selected or {}
    contract = package_outcomes(candidate.package)
    required = next(module for module in contract.modules if module.module_id == 'validation_qa')
    outcomes = []
    for item in required.outcomes:
        reference = selected.get('scenario_attempt_id' if item.method == 'scenario_choice' else 'review_attempt_id')
        outcomes.append({'outcome_id': item.id, 'statement': item.statement, 'method': item.method,
            'attempt_id': reference, 'state': 'selection_required' if reference is None else state})
    status = next((value for value in ('revision_required', 'grading_unavailable', 'assessment_pending', 'selection_required')
        if any(item['state'] == value for item in outcomes)), 'requirements_supported')
    return {'enrollment_id': candidate.progress.enrollment_id, 'course_version': VERSION,
        'manifest_sha256': candidate.package.manifest_sha256, 'module_id': 'validation_qa',
        'rubric_id': contract.rubric_id, 'contract_sha256': encode(contract.model_dump(mode='json'))[1],
        'assessment_kind': 'module_readiness_draft', 'outcomes': outcomes, 'status': status,
        'all_required_outcomes_supported': status == 'requirements_supported', 'read_only': True,
        'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False,
        'selected_receipts': [{'kind': 'automatic_review' if key == 'review_attempt_id' else 'scenario_recognition',
            'attempt_id': value, 'record_sha256': 'a' * 64, 'result_sha256': 'b' * 64} for key, value in selected.items()]}


async def evaluate(candidate, monkeypatch, selected=None, response=None):
    reader = AsyncMock(return_value=response or snapshot(candidate, selected))
    monkeypatch.setattr(ModuleReadiness, 'preview', reader)
    result = await grade(candidate.package, candidate.progress, 'validation_qa', preview=True, assessment_selection=selected)
    reader.assert_awaited_once_with('learner', 'owned-enrollment', 'validation_qa', **(selected or {}))
    return result


async def test_exact_complete_selection_validates_all_outcomes_without_credit_or_progress_write(candidate, monkeypatch):
    before = deepcopy(vars(candidate.progress))
    result = await evaluate(candidate, monkeypatch, SELECTED)
    assert result['passed'] is True and result['stars'] == 1
    assert len(result['checks']) == 3 and all(item['passed'] and item['role'] == 'required' for item in result['checks'])
    assert result['assessment_selection'] == SELECTED
    assert result['assessment_snapshot_sha256'] == encode(result['assessment_snapshot'])[1]
    assert result['credit_awarded'] is result['staff_review_required'] is False
    assert vars(candidate.progress) == before
    with pytest.raises(CourseCatalogError, match='explicitly pinned'):
        pinned_progress('learner')


@pytest.mark.parametrize('selected', [None, {'review_attempt_id': '1' * 32}, {'scenario_attempt_id': '2' * 32}])
async def test_no_implicit_or_partial_selection_earns_a_pass(candidate, monkeypatch, selected):
    result = await evaluate(candidate, monkeypatch, selected)
    assert result['passed'] is False and result['stars'] == 0
    assert any(not item['passed'] for item in result['checks'])


async def test_explicit_failed_outcomes_remain_failed(candidate, monkeypatch):
    result = await evaluate(candidate, monkeypatch, SELECTED, snapshot(candidate, SELECTED, state='revision_required'))
    assert result['passed'] is False and result['stars'] == 0
    assert all(not item['passed'] for item in result['checks'])


@pytest.mark.parametrize('state', ['assessment_pending', 'grading_unavailable'])
async def test_technical_states_do_not_become_a_learner_failure(candidate, monkeypatch, state):
    with pytest.raises(CourseCatalogError, match='no available final assessment'):
        await evaluate(candidate, monkeypatch, SELECTED, snapshot(candidate, SELECTED, state=state))


@pytest.mark.parametrize('change', ['enrollment_id', 'manifest_sha256', 'contract_sha256', 'module_id', 'missing_outcome',
    'method', 'reference', 'summary', 'missing_receipt', 'missing_result', 'credit'])
async def test_mismatched_or_incomplete_original_evidence_never_passes(candidate, monkeypatch, change):
    value = snapshot(candidate, SELECTED)
    if change in ('enrollment_id', 'manifest_sha256', 'contract_sha256', 'module_id'):
        value[change] = 'different'
    elif change == 'missing_outcome':
        value['outcomes'].pop()
    elif change == 'method':
        value['outcomes'][0]['method'] = 'unsupported'
    elif change == 'reference':
        value['outcomes'][0]['attempt_id'] = '3' * 32
    elif change == 'summary':
        value['all_required_outcomes_supported'] = False
    elif change == 'missing_receipt':
        value['selected_receipts'].pop()
    elif change == 'missing_result':
        value['selected_receipts'][0]['result_sha256'] = None
    else:
        value['credit_awarded'] = True
    with pytest.raises(CourseCatalogError):
        await evaluate(candidate, monkeypatch, SELECTED, value)


@pytest.mark.parametrize('unlocked', [False, True])
async def test_required_prior_credit_is_checked_in_the_same_enrollment(candidate, monkeypatch, unlocked):
    candidate.progress.unlocked = unlocked
    def prerequisite(manifest):
        # Exercise the generic runner's support for a different pinned course
        # policy, not a contradiction of the flexible-order policy itself.
        manifest['artifacts'].pop('progression-policy.json')
        next(module for module in manifest['modules'] if module['id'] == 'validation_qa')['prerequisites'] = ['foundations']
    candidate.package = candidate.reload(prerequisite)
    missing = await evaluate(candidate, monkeypatch, SELECTED)
    assert not missing['passed'] and not missing['checks'][-1]['passed']
    candidate.progress.modules['foundations'] = {'completed': True}
    assert (await evaluate(candidate, monkeypatch, SELECTED))['passed']


@pytest.mark.parametrize('change', ['rubric_bytes', 'unverified_contract', 'legacy_stars', 'star_bonus'])
def test_only_exact_verified_single_threshold_packages_load(candidate, change):
    if change == 'rubric_bytes':
        (candidate.folder / 'rubric.py').write_text('raise RuntimeError("unreviewed runner")\n')
    if change == 'unverified_contract':
        contract = json.loads((candidate.folder / 'outcomes.json').read_text())
        contract['state'] = 'design_draft'
        contract['modules'][0]['outcomes'][0]['assessment_status'] = 'implemented'
        (candidate.folder / 'outcomes.json').write_text(json.dumps(contract))
    def changed(manifest):
        # The credit runner must reject these changes independently of the
        # additional policy-integrity guard covered by progression tests.
        manifest['artifacts'].pop('progression-policy.json')
        manifest.update(maximum_stars=3 if change == 'legacy_stars' else 1,
                        star_bonus_xp=25 if change == 'star_bonus' else 0)
    package = candidate.reload(changed)
    with pytest.raises(CourseCatalogError):
        load_rubric(package)


async def test_even_synthetic_verified_draft_is_not_a_supported_credit_course(candidate):
    with pytest.raises(CourseCatalogError, match='supported published'):
        await grade(candidate.package, candidate.progress, 'validation_qa', assessment_selection=SELECTED)


@pytest.mark.parametrize('state,supported,expected', [('draft', False, False), ('published', True, True), ('retired', True, True), ('retired', False, False)])
def test_completion_capability_requires_supported_verified_requirements(candidate, state, supported, expected):
    from dataclasses import replace
    from app.services.certification_versions.grading import selected_outcome_completion_available
    package = replace(candidate.package, entry=candidate.package.entry.model_copy(update={'state': state, 'supported_for_existing': supported}))
    assert selected_outcome_completion_available(package) is expected
    (candidate.folder / 'rubric.py').write_text('raise RuntimeError("unverified")')
    changed = candidate.reload()
    changed = replace(changed, entry=package.entry)
    assert selected_outcome_completion_available(changed) is False
