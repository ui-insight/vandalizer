"""Read-only preservation metadata in real, disposable MongoDB."""
from copy import deepcopy
import json

from app.models.certification import CertificationLabExecution
from app.services.certification_versions.upgrade_comparison import UpgradeComparison
from tests.integration import test_certification_enrollments as fixtures

repo = fixtures.repo
pytestmark = fixtures.pytestmark


async def test_uncertain_run_remains_visible_after_its_write_boundary_has_ended(repo):
    source, target, _ = await fixtures.upgrade_comparison_fixture(repo)
    unresolved = await fixtures.insert_execution_summary(source.user_id, source.uuid, 'uncertain')
    prepared = await fixtures.insert_execution_summary(source.user_id, source.uuid, 'prepared')
    await fixtures.insert_execution_summary('foreign', source.uuid, 'executing')
    collections = (repo.progress, repo.selections, CertificationLabExecution.get_motor_collection())
    before = deepcopy([await collection.find({}).to_list(None) for collection in collections])
    result = await UpgradeComparison(repo).inspect(source.user_id, source.uuid, target)
    assert result['work_in_flight'] is False
    plan = result['preservation_plan']
    assert plan['source_enrollment_id'] == source.uuid
    assert plan['reconciliation_required_count'] == 1
    assert {entry['record_id'] for entry in plan['entries']} == {unresolved['uuid'], prepared['uuid']}
    assert {entry['proposed_action'] for entry in plan['entries']} == {'reconcile_operation', 'retain_unexecuted_work'}
    assert all(entry['module_title'] == 'Foundations' for entry in plan['entries'])
    assert plan['can_activate'] is plan['credit_transferred'] is False
    assert result['target']['transferred_outcome_count'] == 0
    assert 'private' not in json.dumps(plan)
    assert before == [await collection.find({}).to_list(None) for collection in collections]
