"""Saved original finding precedes a changed owned revision and complete joint retest."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_findings as findings
from tests.integration import test_certification_governance_inputs as inputs
from tests.integration import test_certification_governance_preparation as preparation
from tests.integration import test_certification_governance_execution as execution
from tests.integration.test_certification_enrollments import LAB_RUNTIME
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.governance_preparation import GovernancePreparation

repo = findings.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, *, change='funding', capture_before_finding=False):
    f = await findings.fixture(repo)
    if not capture_before_finding:
        f.finding = await findings.submit(repo, f)
    if change == 'funding':
        f.fields[3].searchphrase = 'Return cumulative funds actually obligated in USD under the latest issued amendment, never the planned ceiling or the increment alone.'
        await f.fields[3].save()
    elif change == 'other_field':
        f.fields[0].searchphrase += ' Return the award ID exactly.'
        await f.fields[0].save()
    elif change == 'title_only':
        f.artifact.title += ' Revised title'
        await f.artifact.save()
    f.body['request_id'] = uuid4().hex
    f.corrected = await inputs.capture(repo, f)
    if capture_before_finding:
        f.finding = await findings.submit(repo, f)
    f.plan_body.update(request_id=uuid4().hex, input_snapshot_id=f.corrected['uuid'], input_snapshot_sha256=encode(f.corrected)[1],
        source_finding_id=f.finding['uuid'], source_finding_sha256=encode(f.finding)[1], consent='prepare_repaired_bounded_capstone_extraction')
    return f


async def approved_repair(repo, f):
    f.repair = await preparation.prepare(repo, f)
    f.repair_approval = await preparation.scope(repo, f, f.repair)
    f.execution_body.update(run_id=f.repair['run_id'], plan_sha256=f.repair['plan_sha256'],
        scope_decision_id=f.repair_approval['uuid'], scope_decision_sha256=encode(f.repair_approval)[1])
    return f.repair


async def test_same_artifact_repair_preserves_both_runs_and_decisions_after_live_record_deletion(repo):
    f = await fixture(repo)
    repair = await approved_repair(repo, f)
    assert repair['plan']['phase'] == 'repair' and repair['plan']['changed_fields'] == ['Funds Obligated to Date']
    assert repair['plan']['original_run_id'] == f.original['run_id']
    assert f.repair_approval['prompt']['extraction_phase'] == 'repair'
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f)) as engine:
        final = await execution.execute(repo, f)
        assert engine.call_count == 1
        assert final['state'] == 'completed'
        assert final['result']['repair_checks']['repair_requirements_supported'] is True
        assert final['result']['checks']['source_supported'] is True
        await CertificationLabExecution.get_motor_collection().delete_one({'uuid': f.original['run_id']})
        await CertificationLabInput.get_motor_collection().delete_many({})
        await CertificationLearnerDecision.get_motor_collection().delete_many({})
        assert await preparation.prepare(repo, f, config={}) == final
        assert await execution.execute(repo, f, config={}) == final
        assert engine.call_count == 1
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['unchanged', 'title_only', 'other_field', 'capture_before_finding', 'model', 'finding_hash', 'finding_missing', 'original_consent'])
async def test_repair_cannot_substitute_revision_order_model_or_finding(repo, change):
    f = await fixture(repo, change=change if change in ('unchanged', 'title_only', 'other_field') else 'funding', capture_before_finding=change == 'capture_before_finding')
    config = deepcopy(LAB_RUNTIME)
    if change == 'model':
        config['available_models'][0]['endpoint'] = 'https://example.invalid/changed'
    elif change == 'finding_hash':
        f.plan_body['source_finding_sha256'] = '0' * 64
    elif change == 'finding_missing':
        f.plan_body['source_finding_id'] = uuid4().hex
    elif change == 'original_consent':
        f.plan_body['consent'] = 'prepare_original_bounded_capstone_extraction'
    with pytest.raises(ValueError):
        await preparation.prepare(repo, f, config=config)


@pytest.mark.parametrize('wrong', [True, False])
async def test_actual_repair_values_control_source_support(repo, wrong):
    f = await fixture(repo)
    await approved_repair(repo, f)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f, wrong=wrong)):
        final = await execution.execute(repo, f)
    assert final['result']['repair_checks']['repair_requirements_supported'] is (not wrong)
    assert final['result']['checks']['source_supported'] is (not wrong)


@pytest.mark.parametrize('change', ['finding', 'lineage', 'fields', 'models'])
async def test_rehashed_repair_plan_cannot_replace_its_original_chain(repo, change):
    f = await fixture(repo)
    repair = await preparation.prepare(repo, f)
    raw = await CertificationLabExecution.get_motor_collection().find_one({'uuid': repair['run_id']})
    plan = deepcopy(repair['plan'])
    if change == 'finding':
        plan['source_finding']['submission']['observed_value'] = '180000'
    elif change == 'lineage':
        plan['original_run_sha256'] = '0' * 64
    elif change == 'fields':
        plan['changed_fields'] = []
    else:
        plan['model_names'] = ['invented-model']
    raw['plan_json'], raw['plan_sha256'] = encode(plan)
    with pytest.raises(CourseCatalogError):
        GovernancePreparation.decode(raw)
