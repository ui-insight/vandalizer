"""Dry-run, apply and reconcile the legacy enrollment backfill on synthetic cohorts."""
import asyncio
import datetime
import json
import os
from pathlib import Path
import sys

from bson import json_util
import pytest

from app.models.certification import CertificationEnrollmentSelection
from app.services.certification_versions import legacy_backfill
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.enrollments import EnrollmentRepository, initial_enrollment_id
from tests.integration import test_certification_enrollments as persisted

repo = persisted.repo
pytestmark = persisted.pytestmark
UTC = datetime.timezone.utc


def legacy(user_id, **fields):
    return {'user_id': user_id, 'enrollment_id': None, 'course_version': None, 'modules': {}, 'total_xp': 0,
            'level': 'novice', 'certified': False, 'certified_at': None, 'position_revision': 0,
            'created_at': datetime.datetime(2025, 1, 6, tzinfo=UTC), **fields}


async def seed(repo):
    """Realistic shapes from the unversioned course, including unknown provenance."""
    rows = [
        legacy('unstarted@example.edu'),
        legacy('partial@example.edu', total_xp=125, last_activity_date='2025-02-04', lab_folder_id='lab-folder-1',
               learning_position={'module_id': 'ai_literacy', 'lesson_id': 'ai-lesson-3'}, position_revision=4, modules={
                   'foundations': {'completed': True, 'stars': 1, 'xp_earned': 125, 'attempts': 2, 'completed_at': '2025-02-03',
                                   'provisioned_docs': ['doc-a'], 'self_assessment': {'q1': 'Private reflection', 'q2': 'Another'}},
                   'ai_literacy': {'completed': False, 'attempts': 1, 'self_assessment': {'q1': 'Unfinished'}}}),
        legacy('graduate@example.edu', total_xp=sum(base + 75 for base in (50, 100, 100, 100, 150, 150, 200, 200, 250, 250, 300)),
               level='architect', certified=True, certified_at=datetime.datetime(2025, 6, 1, tzinfo=UTC),
               modules={mid: {'completed': True, 'stars': 3, 'xp_earned': base + 75, 'completed_at': f'2025-05-{index + 1:02d}',
                              'self_assessment': {'q': 'Reflection'}}
                        for index, (mid, base) in enumerate(zip(
                            ['ai_literacy', 'foundations', 'process_mapping', 'workflow_design', 'extraction_engine', 'multi_step',
                             'advanced_nodes', 'output_delivery', 'validation_qa', 'batch_processing', 'governance'],
                            [50, 100, 100, 100, 150, 150, 200, 200, 250, 250, 300]))}),
        legacy('override@example.edu', total_xp=40, unlocked=True,
               modules={'governance': {'completed': False, 'xp_earned': 0}}),
        legacy('duplicate@example.edu', total_xp=100),
        legacy('duplicate@example.edu', total_xp=200),
        legacy('hinted@example.edu', course_version='4.0', total_xp=50,
               modules={'ai_literacy': {'completed': True, 'stars': 3, 'xp_earned': 125}}),
    ]
    await repo.progress.insert_many(rows)
    await repo.progress.insert_one(legacy('lazy@example.edu', total_xp=125,
        modules={'foundations': {'completed': True, 'stars': 1, 'xp_earned': 125}}))
    await repo.ensure_initial('lazy@example.edu')  # Initialized earlier by a normal read.
    await repo.ensure_initial('versioned@example.edu')  # New enrollment, no legacy record.


async def snapshot(repo):
    database = repo.progress.database
    return {name: await database[name].find({}).sort('_id', 1).to_list(None) for name in legacy_backfill.COLLECTIONS.values()}


async def test_dry_run_reads_only_and_classifies_without_identifiers(repo):
    await seed(repo)
    before = await snapshot(repo)
    plan = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    assert await snapshot(repo) == before
    assert plan['dry_run'] is True and plan['can_apply'] is True and plan['legacy_continuation'] == persisted.VERSION
    assert plan['statuses'] == {'already_backfilled': 1, 'needs_reconciliation': 2, 'ready': 4}
    assert plan['reasons_distinct_users'] == {'duplicate_legacy_progress': 1, 'unverified_version_hint': 1}
    assert plan['known_versions'] == {persisted.VERSION: 1}
    assert {row['summary']['historical_version'] for row in plan['users']} == {'legacy_unversioned'}
    assert '@example.edu' not in json_util.dumps(plan) and 'Private reflection' not in json_util.dumps(plan)
    rows = {row['user_key']: row for row in plan['users']}
    partial = rows[legacy_backfill.user_key('partial@example.edu')]['summary']
    assert partial['completed_modules'] == ['foundations'] and partial['stars'] == 1 and partial['total_xp'] == 125
    assert partial['reflections'] == 2 and partial['reflection_answers'] == 3 and partial['lab_folder'] is True
    assert partial['provisioned_docs'] == 1 and partial['learning_position'] is True and partial['xp_explained'] is True
    graduate = rows[legacy_backfill.user_key('graduate@example.edu')]['summary']
    assert graduate['certified'] and graduate['certified_at'].startswith('2025-06-01') and graduate['stars'] == 33
    assert graduate['earliest_completion'] == '2025-05-01' and graduate['latest_completion'] == '2025-05-11'
    assert rows[legacy_backfill.user_key('override@example.edu')]['summary']['unexplained_xp'] == 40


async def test_apply_backfills_reviewed_plan_without_resetting_and_reconciles_every_user(repo):
    await seed(repo)
    plan = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    legacy_before = await repo.progress.find({'enrollment_id': None}).sort('_id', 1).to_list(None)
    result = await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=plan['plan_sha256'])
    assert result['reconciled'] is True and result['backfilled_users'] == 4 and result['failed_users'] == 0
    assert result['totals_before'] == result['totals_after'] == plan['totals']
    assert result['record_counts']['after'] == result['record_counts']['expected_after']
    assert await repo.progress.find({'enrollment_id': None}).sort('_id', 1).to_list(None) == legacy_before
    for user in ('unstarted@example.edu', 'partial@example.edu', 'graduate@example.edu', 'override@example.edu'):
        enrollment = await repo.current(user)
        assert enrollment.uuid == initial_enrollment_id(user) and enrollment.provenance == 'legacy_version_unknown'
        assert enrollment.state == ('completed' if user.startswith('graduate') else 'active')
        progress = await repo.read_progress(user, enrollment.uuid)
        assert progress.enrollment_id == enrollment.uuid  # Bound in memory only; the stored record is unchanged.
    partial = await repo.read_progress('partial@example.edu', initial_enrollment_id('partial@example.edu'))
    assert partial.total_xp == 125 and partial.modules['foundations']['stars'] == 1 and partial.lab_folder_id == 'lab-folder-1'
    assert partial.modules['ai_literacy']['self_assessment'] == {'q1': 'Unfinished'} and partial.position_revision == 4
    for user in ('duplicate@example.edu', 'hinted@example.edu'):
        assert await repo.enrollments.count_documents({'user_id': user}) == 0
        assert await repo.selections.count_documents({'user_id': user}) == 0
    # A finished plan cannot be replayed; a fresh review is idempotent.
    with pytest.raises(legacy_backfill.BackfillChanged):
        await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=plan['plan_sha256'])
    again = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    assert again['statuses'] == {'already_backfilled': 5, 'needs_reconciliation': 2} and again['totals'] == plan['totals']
    repeat = await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=again['plan_sha256'])
    assert repeat['reconciled'] is True and repeat['backfilled_users'] == 0
    assert repeat['record_counts']['before'] == repeat['record_counts']['after']


class CrashingSelections:
    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def update_one(self, *args, **kwargs):
        raise RuntimeError('Synthetic worker crash before selection')


async def test_interrupted_backfill_resumes_without_duplicates(repo, monkeypatch):
    await seed(repo)
    plan = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    with monkeypatch.context() as patch:
        patch.setattr(EnrollmentRepository, 'selections',
                      property(lambda self: CrashingSelections(CertificationEnrollmentSelection.get_motor_collection())))
        with pytest.raises(RuntimeError):
            await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=plan['plan_sha256'])
    resumed = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    assert resumed['statuses'] == {'already_backfilled': 1, 'needs_reconciliation': 2, 'ready': 3, 'resume': 1}
    assert resumed['totals'] == plan['totals']
    result = await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=resumed['plan_sha256'])
    assert result['reconciled'] is True and result['backfilled_users'] == 4
    for user in ('unstarted@example.edu', 'partial@example.edu', 'graduate@example.edu', 'override@example.edu', 'lazy@example.edu'):
        assert await repo.enrollments.count_documents({'user_id': user}) == 1
        assert await repo.selections.count_documents({'user_id': user}) == 1


async def test_changed_records_or_missing_continuation_refuse_to_apply(repo):
    await seed(repo)
    plan = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    await repo.progress.update_one({'user_id': 'partial@example.edu'}, {'$set': {'total_xp': 175}})
    before = await snapshot(repo)
    with pytest.raises(legacy_backfill.BackfillChanged):
        await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=plan['plan_sha256'])
    assert await snapshot(repo) == before
    registry_path = repo.catalog.root / 'registry.json'
    registry = json.loads(registry_path.read_text())
    registry.pop('legacy_continuation')
    registry_path.write_text(json.dumps(registry))
    unconfigured = await legacy_backfill.dry_run(repo.progress.database, repo.catalog)
    assert unconfigured['can_apply'] is False and unconfigured['blockers'] == ['legacy_continuation_not_configured']
    with pytest.raises(CourseCatalogError):
        await legacy_backfill.apply(repo, repo.progress.database, expected_plan_sha256=unconfigured['plan_sha256'])
    assert await snapshot(repo) == before


async def test_operator_script_dry_runs_then_applies_only_the_reviewed_plan(repo):
    await seed(repo)
    script = Path(__file__).resolve().parents[3] / 'scripts/backfill_certification_enrollments.py'
    base = [sys.executable, str(script), '--database', repo.progress.database.name, '--catalog-root', str(repo.catalog.root)]
    env = {**os.environ, 'CERTIFICATION_BACKFILL_MONGO_URL': os.environ['CERTIFICATION_TEST_MONGO_URL']}

    async def run(*extra, environment=env):
        process = await asyncio.create_subprocess_exec(*base, *extra, env=environment,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await process.communicate()
        return process.returncode, out.decode(), err.decode()

    before = await snapshot(repo)
    code, _, err = await run(environment={k: v for k, v in env.items() if k != 'CERTIFICATION_BACKFILL_MONGO_URL'})
    assert code == 1 and 'mongodb://' not in err
    code, out, _ = await run()
    plan = json.loads(out)
    assert code == 0 and plan['dry_run'] is True and plan['statuses']['ready'] == 4
    assert await snapshot(repo) == before
    code, _, _ = await run('--apply')
    assert code == 2 and await snapshot(repo) == before  # An unreviewed apply is refused.
    code, out, _ = await run('--apply', '--expected-plan-sha256', plan['plan_sha256'])
    result = json.loads(out)
    assert code == 0 and result['reconciled'] is True and result['backfilled_users'] == 4
