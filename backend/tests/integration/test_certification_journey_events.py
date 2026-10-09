import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.models.certification_journey import CertificationJourneyEvent
from app.routers.certification_journey import router
from app.services.certification_versions.course_health import course_health
from app.services.certification_versions.journey_events import JourneyEventRequest, JourneyEventConflict, record
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


def request(enrollment=None, event='initial_progress_load_failed', **changes):
    return JourneyEventRequest(event_id=uuid4().hex, event=event,
        **({'enrollment_id': enrollment.uuid, 'manifest_sha256': enrollment.manifest_sha256} if enrollment else {}), **changes)


async def test_duplicate_delivery_is_one_observation_and_preserves_all_learning_state(repo):
    enrollment = await repo.ensure_initial('learner')
    progress = (await repo.read_progress('learner', enrollment.uuid)).model_dump()
    event = request(enrollment, 'bridge_assessment_requested')
    results = await asyncio.gather(*(record('learner', event) for _ in range(4)))
    assert all(row == {'recorded': True, 'assessment_changed': False} for row in results)
    assert await CertificationJourneyEvent.get_motor_collection().count_documents({}) == 1
    assert (await repo.read_progress('learner', enrollment.uuid)).model_dump() == progress
    assert (await repo._enrollment('learner', enrollment.uuid)).model_dump() == enrollment.model_dump()
    with pytest.raises(JourneyEventConflict):
        await record('learner', event.model_copy(update={'event': 'position_save_failed'}))


async def test_another_learner_or_wrong_package_cannot_attribute_an_event(repo):
    enrollment = await repo.ensure_initial('learner')
    for user, body in [('other', request(enrollment)), ('learner', request(enrollment).model_copy(update={'manifest_sha256': 'f' * 64}))]:
        with pytest.raises(JourneyEventConflict):
            await record(user, body)
    assert await CertificationJourneyEvent.get_motor_collection().count_documents({}) == 0


async def test_initial_load_failure_does_not_create_a_course_and_legacy_identity_stays_unknown(repo):
    await record('not-started', request())
    assert await repo.current('not-started') is None
    enrollment = await repo.ensure_initial('legacy')
    await repo.enrollments.update_one({'uuid': enrollment.uuid}, {'$set': {'provenance': 'legacy_version_unknown'}})
    await record('legacy', request(enrollment, 'saved_lesson_displayed'))
    rows = await CertificationJourneyEvent.get_motor_collection().find({}).to_list(None)
    assert all(row['course_version'] is None and row['manifest_sha256'] is None for row in rows)


async def test_aggregate_window_privacy_and_retention_are_explicit(repo):
    enrollment = await repo.ensure_initial('PRIVATE-LEARNER')
    for event in ('initial_progress_load_failed', 'progress_refresh_failed', 'position_save_failed', 'saved_lesson_displayed', 'bridge_assessment_requested'):
        await record('PRIVATE-LEARNER', request(enrollment, event))
    collection = CertificationJourneyEvent.get_motor_collection()
    await collection.insert_one({'uuid': uuid4().hex, 'user_id': 'PRIVATE', 'state': 'position_save_failed',
                                 'observed_at': datetime.now(timezone.utc) - timedelta(days=31)})
    await collection.insert_one({'uuid': uuid4().hex, 'user_id': 'PRIVATE', 'state': 'position_save_failed',
                                 'observed_at': datetime.now(timezone.utc) + timedelta(days=1)})
    report = await course_health()
    assert report['journey']['window_days'] == 30
    assert len(report['journey']['rows']) == 5 and sum(row['count'] for row in report['journey']['rows']) == 5
    assert 'PRIVATE' not in json.dumps(report) and enrollment.uuid not in json.dumps(report)
    indexes = await collection.index_information()
    assert any(index.get('expireAfterSeconds') == 90 * 24 * 60 * 60 for index in indexes.values())
    if os.environ.get('CERTIFICATION_JOURNEY_EXPORT'):
        Path(os.environ['CERTIFICATION_JOURNEY_EXPORT']).write_text(json.dumps(report, indent=2) + '\n')


async def test_http_refuses_free_text_course_spoofing_and_unbound_success(repo):
    app = FastAPI()
    app.include_router(router, prefix='/api/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='learner')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        for extra in ({'answers': 'PRIVATE'}, {'course_version': 'spoof'}, {'event': 'arbitrary'}, {'event': 'saved_lesson_displayed'}):
            response = await http.post('/api/certification/journey-events', json=request().model_dump() | extra)
            assert response.status_code == 422
        response = await http.post('/api/certification/journey-events', json=request().model_dump())
        assert response.status_code == 200 and response.json()['assessment_changed'] is False
    assert await CertificationJourneyEvent.get_motor_collection().count_documents({}) == 1
