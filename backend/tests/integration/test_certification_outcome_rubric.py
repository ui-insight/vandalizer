"""Runner reads actual saved receipts; synthetic release flags are not calibration."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.certification import CertificationReviewAttempt, CertificationScenarioAttempt
from app.services.certification_versions import module_readiness
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.grading import grade
from app.services.certification_versions.rubrics import competency_v5
from app.services.certification_versions.scenario_submissions import module_bank
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_reviews as validation

repo = base.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, monkeypatch, *, wrong_execution=False, single_module=False):
    original = repo.ensure_initial
    async def initialize(user_id):
        # Install the exact runner in the isolated synthetic package BEFORE
        # enrollment or evidence creation. Never rewrite saved course identity.
        registry_path = repo.catalog.root / 'registry.json'
        registry = json.loads(registry_path.read_text())
        version = registry['new_enrollment_default']
        folder = repo.catalog.root / version
        (folder / 'rubric.py').write_bytes(Path(competency_v5.__file__).read_bytes())
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest.update(maximum_stars=1, star_bonus_xp=0)
        if single_module:
            manifest['title'] = 'Synthetic one-module outcome course'
            manifest['modules'] = [item for item in manifest['modules'] if item['id'] == 'validation_qa']
            for name in ('lessons.json', 'exercises.json'):
                value = json.loads((folder / name).read_text())
                (folder / name).write_text(json.dumps({'validation_qa': value['validation_qa']}))
            panel = json.loads((folder / 'panel-modules.json').read_text())
            (folder / 'panel-modules.json').write_text(json.dumps([item for item in panel if item['id'] == 'validation_qa']))
            contract = json.loads((folder / 'outcomes.json').read_text())
            contract['modules'] = [item for item in contract['modules'] if item['module_id'] == 'validation_qa']
            (folder / 'outcomes.json').write_text(json.dumps(contract))
            structure = json.loads((folder / 'course-structure.json').read_text())
            structure['levels'] = [{'name': 'novice', 'xp': 0}, {'name': 'validated', 'xp': manifest['modules'][0]['base_xp']}]
            structure['tiers'] = [{**tier, 'moduleIds': ['validation_qa']} for tier in structure['tiers'] if 'validation_qa' in tier['moduleIds']]
            (folder / 'course-structure.json').write_text(json.dumps(structure))
            for name in list(manifest['artifacts']):
                if name.startswith('assessments/') and name != 'assessments/validation_qa.json':
                    del manifest['artifacts'][name]
            for name in manifest['artifacts']:
                manifest['artifacts'][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        manifest['artifacts']['rubric.py'] = hashlib.sha256((folder / 'rubric.py').read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        registry['releases'][version]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        registry_path.write_text(json.dumps(registry))
        return await original(user_id)
    monkeypatch.setattr(repo, 'ensure_initial', initialize)
    f = await validation.fixture(repo, corrected_wrong=wrong_execution)
    monkeypatch.setattr(repo, 'ensure_initial', original)
    monkeypatch.setattr(module_readiness, 'EnrollmentRepository', lambda: repo)
    submission = await validation.submit(repo, f)
    prepared = await validation.prepare(repo, f, submission['uuid'])
    judge = AsyncMock(side_effect=base.supported_review)
    await base.evaluate_review(repo, f.learner, f.package, prepared['attempt_id'], judge)
    bank = module_bank(f.package, 'validation_qa')
    failed, passed = uuid4().hex, uuid4().hex
    await base.submit_scenario(repo, f.learner, f.package, bank, {}, failed)
    await base.submit_scenario(repo, f.learner, f.package, bank, {q.id: q.correct_choice_id for q in bank.questions}, passed)
    return f, prepared['attempt_id'], failed, passed, judge


@pytest.mark.parametrize('wrong_execution', [False, True])
async def test_runner_requires_complete_selected_originals_and_preserves_saved_execution_veto(repo, monkeypatch, wrong_execution):
    f, review, failed, passed, judge = await fixture(repo, monkeypatch, wrong_execution=wrong_execution)
    progress = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    before = await repo.progress.find_one({'user_id': f.learner.user_id})
    reviews = await CertificationReviewAttempt.get_motor_collection().find({}).to_list(None)
    scenarios = await CertificationScenarioAttempt.get_motor_collection().find({}).to_list(None)
    missing = await grade(f.package, progress, 'validation_qa', assessment_selection={'review_attempt_id': review})
    assert not missing['passed']
    assert any(not item['passed'] and 'Explicitly select' in item['detail'] for item in missing['checks'])
    original_failure = await grade(f.package, progress, 'validation_qa', assessment_selection={'review_attempt_id': review, 'scenario_attempt_id': failed})
    assert not original_failure['passed']
    complete = await grade(f.package, progress, 'validation_qa', assessment_selection={'review_attempt_id': review, 'scenario_attempt_id': passed})
    assert complete['passed'] is (not wrong_execution)
    assert complete['stars'] == (0 if wrong_execution else 1)
    assert complete['credit_awarded'] is False
    assert complete['assessment_snapshot']['selected_receipts'][0]['attempt_id'] == review
    assert await repo.progress.find_one({'user_id': f.learner.user_id}) == before
    assert await CertificationReviewAttempt.get_motor_collection().find({}).to_list(None) == reviews
    assert await CertificationScenarioAttempt.get_motor_collection().find({}).to_list(None) == scenarios
    judge.assert_awaited_once()


async def test_missing_original_receipt_is_a_controlled_selection_error(repo, monkeypatch):
    f, _, _, passed, judge = await fixture(repo, monkeypatch)
    progress = await repo.read_progress(f.learner.user_id, f.learner.uuid)
    with pytest.raises(EnrollmentConflict, match='unavailable for this enrollment'):
        await grade(f.package, progress, 'validation_qa', assessment_selection={'review_attempt_id': uuid4().hex, 'scenario_attempt_id': passed})
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0
    judge.assert_awaited_once()
