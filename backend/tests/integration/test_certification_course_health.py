"""Read-only course census: real aggregate pipelines and HTTP authorization."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pymongo.errors import OperationFailure

from app.dependencies import get_current_user
from app.models.certification import CertificationEnrollment, CertificationProgress
from app.models.certification_journey import CertificationJourneyEvent
from app.routers import admin
from app.services.certification_versions import course_health as health
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark
PRIVATE = 'PRIVATE learner answer and document contents'


def client(*, is_admin=False, is_staff=False):
    app = FastAPI()
    app.include_router(admin.router, prefix='/api/admin')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=is_admin, is_staff=is_staff)
    return AsyncClient(transport=ASGITransport(app=app), base_url='http://test')


async def insert(source, **metadata):
    return await health.SOURCES[source][0].get_motor_collection().insert_one({
        'uuid': uuid4().hex, 'user_id': PRIVATE, 'record_json': PRIVATE,
        'validation_json': PRIVATE, 'result_json': PRIVATE,
        'course_version': 'course-v5', 'manifest_sha256': 'a' * 64, **metadata,
    })


async def snapshot():
    return {source: await model.get_motor_collection().find({}).to_list(None)
            for source, (model, _) in health.SOURCES.items()}


async def test_actual_aggregation_keeps_packages_states_and_upgrade_provenance_separate(repo):
    await insert('enrollments', state='active', provenance='new_enrollment')
    await insert('enrollments', state='prepared', provenance='explicit_upgrade')
    await insert('enrollments', state='active', provenance='explicit_upgrade', manifest_sha256='b' * 64)
    for source, state in [('automatic_reviews', 'unavailable'), ('lab_runs', 'uncertain'),
                          ('lab_runs', 'failed'), ('module_completions', 'rejected'), ('module_completions', 'applied')]:
        await insert(source, state=state)
    before = await snapshot()
    async with client(is_admin=True) as http:
        response = await http.get('/api/admin/certifications/health')
    assert response.status_code == 200
    report = response.json()
    assert report['read_only'] and report['scope'] == 'all_retained_records'
    assert report['started_at'] <= report['observed_at']
    assert len(report['rows']) == 8 and all(row['count'] == 1 for row in report['rows'])
    assert {row['manifest_sha256'] for row in report['rows']} == {'a' * 64, 'b' * 64}
    assert {row['state'] for row in report['rows'] if row['source'] == 'module_completions'} == {'rejected', 'applied'}
    assert report['unavailable_metrics'] == ['dropout', 'grading_question_outcomes']
    assert report['journey']['rows'] == []
    assert PRIVATE not in json.dumps(report) and 'user_id' not in json.dumps(report)
    assert await snapshot() == before


async def enrollment(user, *, state='active', provenance='new_enrollment', days_ago=0, manifest='a' * 64, version='course-v5',
                     saved_days_ago=None, attempt_days_ago=None):
    now = datetime.now(timezone.utc)
    progress_id = ObjectId()
    uuid = uuid4().hex
    await CertificationProgress.get_motor_collection().insert_one({
        '_id': progress_id, 'user_id': user, 'modules': {'m': {'answers': PRIVATE}},
        **({'learning_position': {'lesson_id': PRIVATE, 'saved_at': (now - timedelta(days=saved_days_ago)).isoformat()}}
           if saved_days_ago is not None else {})})
    await CertificationEnrollment.get_motor_collection().insert_one({
        'uuid': uuid, 'user_id': user, 'course_version': version, 'manifest_sha256': manifest,
        'progress_id': str(progress_id), 'provenance': provenance, 'state': state,
        'created_at': now - timedelta(days=days_ago)})
    if attempt_days_ago is not None:
        await insert('module_completions', user_id=user, enrollment_id=uuid, state='applied',
                     course_version=version, manifest_sha256=manifest, created_at=now - timedelta(days=attempt_days_ago))
    return uuid


async def journey(state, count, manifest='a' * 64):
    for _ in range(count):
        await CertificationJourneyEvent.get_motor_collection().insert_one({
            'uuid': uuid4().hex, 'user_id': PRIVATE, 'state': state, 'course_version': 'course-v5',
            'manifest_sha256': manifest, 'observed_at': datetime.now(timezone.utc) - timedelta(days=1)})


def course_row(report, version='course-v5'):
    return next(row for row in report['journey_success']['courses'] if row['course_version'] == version)


async def test_inactivity_uses_latest_server_activity_and_is_not_dropout(repo):
    await enrollment('old-but-reading', days_ago=200, saved_days_ago=3)
    await enrollment('old-but-submitting', days_ago=200, attempt_days_ago=10)
    await enrollment('quiet', days_ago=61)
    await enrollment('recent', days_ago=59)
    await enrollment('quiet-done', state='completed', days_ago=300)
    await enrollment('quiet-prepared', state='prepared', days_ago=300)
    report = await health.course_health()
    row = course_row(report)
    assert report['journey_success']['inactive_after_days'] == 60
    assert (row['started'], row['active'], row['completed'], row['inactive'], row['activity_unknown']) == (5, 4, 1, 1, 0)
    assert row['completion_rate'] == 0.2 and row['inactive_share'] is None  # four active is below the rate floor
    assert 'dropout' in report['unavailable_metrics'] and PRIVATE not in json.dumps(report)


async def test_rates_disputes_resume_and_bridge_uptake_are_counted_by_version(repo, monkeypatch):
    for index, state in enumerate(['completed', 'completed', 'transferred', 'active', 'active', 'active']):
        await enrollment(f'learner-{index}', state=state)
    for index in range(5):
        await enrollment(f'legacy-{index}', provenance='legacy_version_unknown', version='legacy-v4', manifest='c' * 64)
    for index in range(2):
        await enrollment(f'legacy-{index}', provenance='explicit_upgrade')
    await enrollment('legacy-4', provenance='explicit_upgrade', state='prepared')  # not a start
    await insert('automatic_reviews', state='evaluated', parent_attempt_id=uuid4().hex)
    await insert('automatic_reviews', state='evaluated')
    await journey('grading_question_opened', 3)
    await journey('saved_lesson_displayed', 4)
    await journey('saved_lesson_unavailable', 1)
    report = await health.course_health()
    row = course_row(report)
    assert row['started'] == 8 and row['completed'] == 2 and row['transferred'] == 1
    assert row['completion_rate'] == round(2 / 7, 4)
    assert row['staff_grading_corrections'] == 1 and row['grading_questions_opened'] == 3
    assert (row['resumes_restored'], row['resumes_unavailable'], row['resume_success_rate']) == (4, 1, 0.8)
    bridge = report['journey_success']['bridge']
    assert (bridge['legacy_learners'], bridge['upgraded_learners'], bridge['uptake_rate']) == (5, 2, 0.4)
    assert bridge['targets'] == [{'course_version': 'course-v5', 'manifest_sha256': 'a' * 64, 'learners': 2, 'course_title': None}]
    legacy = next(row for row in report['journey_success']['courses'] if row['course_version'] is None)
    assert legacy['started'] == 5
    text = json.dumps(report)
    assert PRIVATE not in text and 'legacy-0' not in text and 'learner-0' not in text


async def test_registered_package_reports_its_plain_course_title(repo, monkeypatch):
    monkeypatch.setattr(health, 'CourseCatalog', lambda: repo.catalog)
    version = base.VERSION
    manifest = repo.catalog.registry()['releases'][version]['manifest_sha256']
    await enrollment('learner', version=version, manifest=manifest)
    await enrollment('other-package', version=version, manifest='d' * 64)
    report = await health.course_health()
    titles = {row['manifest_sha256']: row['course_title'] for row in report['journey_success']['courses']}
    assert titles == {manifest: repo.catalog.load(version, preview=True).manifest.title, 'd' * 64: None}


async def test_unknown_history_and_malformed_metadata_do_not_leak_or_imply_a_version(repo):
    await insert('enrollments', state='active', provenance='legacy_version_unknown')
    await insert('lab_runs', state=PRIVATE, course_version={'secret': PRIVATE}, manifest_sha256=PRIVATE)
    report = await health.course_health()
    legacy = next(row for row in report['rows'] if row['source'] == 'enrollments')
    invalid = next(row for row in report['rows'] if row['source'] == 'lab_runs')
    assert legacy['course_version'] is None and legacy['manifest_sha256'] is None
    assert invalid['course_version'] is None and invalid['manifest_sha256'] is None and invalid['state'] == 'unknown'
    assert PRIVATE not in json.dumps(report)


async def test_empty_collections_are_distinct_from_unavailable_metrics_and_staff_can_read(repo):
    async with client(is_staff=True) as http:
        response = await http.get('/api/admin/certifications/health')
    assert response.status_code == 200
    assert response.json()['rows'] == [] and response.json()['unavailable_metrics']
    assert all(not rows for rows in (await snapshot()).values())


async def test_unauthorized_user_cannot_trigger_an_aggregate(repo, monkeypatch):
    read = AsyncMock(side_effect=AssertionError('Authorization must precede any read'))
    monkeypatch.setattr(health, 'course_health', read)
    async with client() as http:
        response = await http.get('/api/admin/certifications/health')
    assert response.status_code == 403
    read.assert_not_awaited()


async def test_group_limit_fails_report_instead_of_returning_partial_counts(repo, monkeypatch):
    monkeypatch.setattr(health, 'MAX_GROUPS', 1)
    await insert('enrollments', state='prepared', provenance='explicit_upgrade')
    await insert('enrollments', state='active', provenance='explicit_upgrade')
    async with client(is_admin=True) as http:
        response = await http.get('/api/admin/certifications/health')
    assert response.status_code == 503 and 'rows' not in response.json()


async def test_database_failure_does_not_become_empty_success_or_expose_query_details(repo, monkeypatch):
    monkeypatch.setattr(health, 'course_health', AsyncMock(side_effect=OperationFailure(PRIVATE)))
    async with client(is_admin=True) as http:
        response = await http.get('/api/admin/certifications/health')
    assert response.status_code == 503 and PRIVATE not in response.text
