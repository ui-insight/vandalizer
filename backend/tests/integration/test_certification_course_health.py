"""Read-only course census: real aggregate pipelines and HTTP authorization."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pymongo.errors import OperationFailure

from app.dependencies import get_current_user
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
    assert 'bridge_uptake' in report['unavailable_metrics'] and 'abandonment_rate' in report['unavailable_metrics']
    assert PRIVATE not in json.dumps(report) and 'user_id' not in json.dumps(report)
    assert await snapshot() == before


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
