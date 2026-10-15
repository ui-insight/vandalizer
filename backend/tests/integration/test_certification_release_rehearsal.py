"""Rehearse the QA staging release path against a disposable database.

Uses the operator script and the deployment's own configuration mechanism
(CERTIFICATION_CATALOG_ROOT, CERTIFICATION_VERSIONING_ENABLED, ENVIRONMENT):
draft catalog, publication, default switch, interrupted initialization,
notification deduplication, a worker missing the release, rollback with the flag
off and back on, and production refusal. Only synthetic learners exist; the
application catalog is never written.
"""
import asyncio
import datetime
import importlib.util
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from app.models.certification import CertificationEnrollment, CertificationProgress
from app.models.notification import Notification
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.cohort_inventory import inventory
from app.services.certification_versions.completion_notices import CompletionNoticeRepository
from app.services.certification_versions.course_health import course_health
from app.services.certification_versions.credentials import CredentialRepository, CredentialSnapshot
from app.services.certification_versions.delivery import CourseDelivery
from app.services.certification_versions.enrollments import EnrollmentRepository
from app.services.certification_versions.readers import course_incident, existing_active_progress, support_metadata
from app.services.certification_versions.release_coherence import deployment_identity
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark
spec = importlib.util.spec_from_file_location('stage_qa', Path(__file__).resolve().parents[3] / 'scripts/stage_certification_v5_qa.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
RELEASE = 'v5.0-qa-rehearsal.1'
LEGACY = stage.LEGACY


def deploy(monkeypatch, catalog_root, *, enabled=True, environment='staging'):
    """What an operator sets on every API and Celery worker."""
    monkeypatch.setenv('CERTIFICATION_CATALOG_ROOT', str(catalog_root))
    monkeypatch.setenv('CERTIFICATION_VERSIONING_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('ENVIRONMENT', environment)
    monkeypatch.setenv('JWT_SECRET_KEY', 'synthetic-rehearsal-secret-' + 'x' * 40)


async def stored(user_id):
    """Raw learner records, for before/after preservation checks."""
    collections = (CertificationEnrollment, CertificationProgress)
    rows = []
    for model in collections:
        rows.extend(sorted(await model.get_motor_collection().find({'user_id': user_id}).to_list(None), key=lambda row: str(row['_id'])))
    return rows


async def observed_inventory():
    database = CertificationProgress.get_motor_collection().database
    return await inventory(database, max_records=1000)


async def test_qa_staging_release_rehearsal(repo, tmp_path, monkeypatch):
    application_registry = (CATALOG_ROOT / 'registry.json').read_bytes()
    staging = tmp_path / 'staging-catalog'
    manifests = stage.prepare(staging, RELEASE)
    assert set(manifests) == {LEGACY, RELEASE}
    deploy(monkeypatch, staging)
    assert EnrollmentRepository().catalog.root == staging.resolve()

    # Existing learner with unversioned history, before anything is published.
    legacy_doc = CertificationProgress(user_id='legacy-learner', modules={'ai_literacy': {'completed': True, 'xp_earned': 100}},
                                       total_xp=100)
    await legacy_doc.insert()
    legacy_before = await stored('legacy-learner')

    # Enabling the flag before publication fails closed instead of guessing a course.
    with pytest.raises(CourseCatalogError, match='No supported initial course'):
        await EnrollmentRepository().ensure_initial('early-learner')

    # Draft -> published baseline, chosen for unknown legacy history and new learners.
    catalog = CourseCatalog()
    stage.publish(catalog, LEGACY, expected_digest=manifests[LEGACY])
    stage.choose_default(catalog, LEGACY, legacy_continuation=True)
    stage.choose_default(catalog, LEGACY)
    before_switch = await EnrollmentRepository().ensure_initial('learner-a')
    assert before_switch.course_version == LEGACY

    # Draft -> QA staging publication and default switch, through the operator script.
    notifications_before = await Notification.get_motor_collection().count_documents({})
    published = stage.publish_qa(staging, inventory=await observed_inventory(), reason='Rehearse QA staging', actor='rehearsal')
    assert published['registry']['new_enrollment_default'] == RELEASE
    assert published['registry']['releases'][RELEASE]['mode'] == 'qa_staging'
    assert published['changes']['target_manifest_sha256'] == manifests[RELEASE]
    # Restarting the publish step after an interruption is a no-op on the recorded publication.
    again = stage.publish_qa(staging, inventory=await observed_inventory(), reason='Rehearse QA staging', actor='rehearsal')
    assert again['changes']['report_sha256'] == published['changes']['report_sha256']
    assert await Notification.get_motor_collection().count_documents({}) == notifications_before

    learner_b = await EnrollmentRepository().ensure_initial('learner-b')
    assert learner_b.course_version == RELEASE and learner_b.manifest_sha256 == manifests[RELEASE]
    assert (await EnrollmentRepository().current('learner-a')).course_version == LEGACY
    continuation = await EnrollmentRepository().ensure_initial('legacy-learner')
    assert continuation.course_version == LEGACY and continuation.provenance == 'legacy_version_unknown'
    preserved = await EnrollmentRepository().read_progress('legacy-learner', continuation.uuid)
    assert (preserved.total_xp, str(preserved.id)) == (100, str(legacy_doc.id))
    assert [row for row in await stored('legacy-learner') if 'modules' in row][0]['modules'] == legacy_before[0]['modules']

    # Initialization interrupted between its inserts and the selection restarts cleanly.
    interrupted = EnrollmentRepository()
    original = interrupted.read_progress
    calls = {'count': 0}
    async def crash_once(*args, **kwargs):
        calls['count'] += 1
        if calls['count'] == 1:
            raise RuntimeError('worker stopped')
        return await original(*args, **kwargs)
    monkeypatch.setattr(interrupted, 'read_progress', crash_once)
    with pytest.raises(RuntimeError):
        await interrupted.ensure_initial('learner-c')
    assert await interrupted.selections.find_one({'user_id': 'learner-c'}) is None
    resumed = await interrupted.ensure_initial('learner-c')
    assert resumed.course_version == RELEASE
    assert await interrupted.enrollments.count_documents({'user_id': 'learner-c'}) == 1
    assert await interrupted.progress.count_documents({'user_id': 'learner-c'}) == 1

    # Learner B works in the 5.0 course.
    course = await CourseDelivery().course('learner-b', learner_b.uuid)
    first_module = course['modules'][0]
    first_lesson = first_module['lessons'][0]
    saved = await CourseDelivery().save_position('learner-b', learner_b.uuid, first_module['id'], first_lesson['id'])
    assert saved['course_version'] == RELEASE
    work_before = await stored('learner-b')

    # Completion notices stay single under replay and concurrency.
    credential = CredentialSnapshot(credential_id=uuid4().hex, user_id='learner-b', enrollment_id=learner_b.uuid,
        learner_name='Synthetic Learner', course_title=stage.TITLE, course_version=RELEASE,
        manifest_sha256=manifests[RELEASE], rubric_id='v5.0-competency-draft.1', provenance='versioned_course_completion',
        certified_at='2026-10-15T12:00:00+00:00', recorded_at='2026-10-15T12:01:00+00:00',
        level='synthetic', module_ids=('ai_literacy',), evidence=(), outcomes=('outcome-one',))
    await CredentialRepository().persist(credential)
    notices = CompletionNoticeRepository()
    prepared = await asyncio.gather(*(notices.prepare('learner-b', learner_b.uuid) for _ in range(3)))
    await asyncio.gather(*(notices.notify(row) for row in prepared))
    await notices.notify(await notices.prepare('learner-b', learner_b.uuid))
    assert await Notification.get_motor_collection().count_documents({'user_id': 'learner-b', 'kind': 'certification_complete'}) == 1
    assert await notices.records.count_documents({'user_id': 'learner-b'}) == 1

    # Incident: one worker is missing the 5.0 package. Support can name it; work is untouched.
    healthy = deployment_identity()
    broken = tmp_path / 'worker-without-release'
    shutil.copytree(staging, broken)
    shutil.rmtree(broken / RELEASE)
    registry = json.loads((broken / 'registry.json').read_text())
    registry['releases'].pop(RELEASE)
    registry['new_enrollment_default'] = LEGACY
    (broken / 'registry.json').write_text(json.dumps(registry))
    deploy(monkeypatch, broken)
    assert deployment_identity()['fingerprint'] != healthy['fingerprint']
    with pytest.raises(CourseCatalogError) as failure:
        await existing_active_progress('learner-b')
    explanation = await course_incident('learner-b', None, failure.value)
    assert 'does not have the course version' in explanation and 'not changed' in explanation
    rows = await CertificationProgress.find({'user_id': 'learner-b'}).to_list()
    metadata = await support_metadata(rows[0])
    assert metadata['course_version'] == RELEASE and 'does not have the course version' in metadata['reconciliation_error']
    health = await course_health()
    assert [item['status'] for item in health['release_incidents'] if item['course_version'] == RELEASE] == ['unknown_on_this_worker']
    assert health['release_identity']['fingerprint'] != healthy['fingerprint']
    assert await stored('learner-b') == work_before

    # Production refuses the QA release even with the right catalog.
    deploy(monkeypatch, staging, environment='production')
    with pytest.raises(CourseCatalogError, match='QA staging only'):
        await existing_active_progress('learner-b')
    assert 'QA staging only' in await course_incident('learner-b', None, CourseCatalogError('Course unavailable'))

    # Rollback: new learners return to the baseline, 5.0 closes to new enrollment,
    # existing 5.0 work stays pinned, then the flag goes off and back on.
    deploy(monkeypatch, staging)
    rolled = stage.rollback(staging)
    assert rolled['registry']['new_enrollment_default'] == LEGACY
    assert rolled['registry']['releases'][RELEASE]['state'] == 'retired'
    assert (await EnrollmentRepository().ensure_initial('learner-d')).course_version == LEGACY
    deploy(monkeypatch, staging, enabled=False)
    still_selected = await existing_active_progress('learner-b')
    assert still_selected.course_version == RELEASE
    assert await stored('learner-b') == work_before
    deploy(monkeypatch, staging)
    resumed_course = await CourseDelivery().course('learner-b', learner_b.uuid)
    assert resumed_course['course_version'] == RELEASE and resumed_course['state'] == 'retired'
    assert resumed_course['progress']['learning_position']['lesson_id'] == first_lesson['id']
    with pytest.raises(CourseCatalogError, match='closed to new enrollments'):
        CourseCatalog().load(RELEASE, new_enrollment=True)
    assert await stored('learner-b') == work_before
    assert (CATALOG_ROOT / 'registry.json').read_bytes() == application_registry
    assert datetime.datetime.fromisoformat(rolled['registry']['observed_at']).tzinfo is not None
