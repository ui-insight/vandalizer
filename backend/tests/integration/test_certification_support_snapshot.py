"""Read-only support uses original course metadata, never private learner work."""
import datetime
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies import get_current_user
from app.models.certification import CertificationProgress
from app.routers import admin
from app.services.certification_versions import enrollments, readers
from app.services.certification_versions.attempts import AttemptRepository, encode, progress_digest
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.outcomes import package_outcomes
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

repo = base.repo
pytestmark = base.pytestmark
SECRET = 'PRIVATE SOURCE AND REFLECTION MUST NOT LEAVE STORAGE'


async def setup(repo, monkeypatch, tmp_path):
    fixture = candidate.__wrapped__(tmp_path)
    path = fixture.folder.parent / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    path.write_text(json.dumps(registry))
    repo.catalog = CourseCatalog(fixture.folder.parent)
    enrollment = await repo.ensure_initial('support-learner')
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='operator', is_admin=False, is_staff=True)
    client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
    return enrollment, fixture.package, app, client


async def record(repo, enrollment, package, **changes):
    progress = await repo.read_progress(enrollment.user_id, enrollment.uuid)
    row = dict(uuid=uuid4().hex, user_id=enrollment.user_id, enrollment_id=enrollment.uuid,
               course_version=enrollment.course_version, manifest_sha256=package.manifest_sha256,
               rubric_id=package.manifest.rubric_id, module_id=package.manifest.modules[0].id,
               state='applied', created_at=datetime.datetime.now(datetime.timezone.utc),
               progress_sha256=progress_digest(progress), progress_json=SECRET)
    row.update(changes)
    if row['state'] in ('graded', 'applied', 'rejected') and 'validation_json' not in row:
        row['validation_json'], row['validation_sha256'] = encode({'passed': row['state'] != 'rejected', 'checks': []})
    if row['state'] in ('applied', 'rejected', 'failed') and 'result_json' not in row:
        result = {'attempt_id': row['uuid'], 'private_extra': SECRET}
        if row['state'] == 'failed':
            result.update(error='Original technical failure', failure_kind='execution')
        else:
            result['validation'] = json.loads(row['validation_json'])
            if row['state'] == 'rejected':
                result['error'] = 'Validation did not pass'
            else:
                result.update({key: row[key] for key in ('module_id', 'enrollment_id', 'course_version', 'manifest_sha256')})
        row['result_json'], row['result_sha256'] = encode(result)
    await AttemptRepository().records.insert_one(row)
    return row


async def snapshot(repo):
    db = repo.progress.database
    return {name: await db[name].find({}).to_list(None) for name in await db.list_collection_names()}


async def read(client, enrollment):
    return await client.get('/admin/certifications/' + enrollment.user_id, params={'enrollment_id': enrollment.uuid})


async def test_original_position_failed_outcomes_and_evidence_references_are_private_read_only(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    module = package.manifest.modules[0]
    lesson = package.json('lessons.json')[module.id]['lessons'][0]
    position = dict(module_id=module.id, lesson_id=lesson['id'], revision=lesson['revision'],
                    content_sha256=hashlib.sha256(lesson['content'].encode()).hexdigest(), saved_at='2026-10-08T10:00:00+00:00')
    await repo.progress.update_one({'user_id': enrollment.user_id}, {'$set': {
        'learning_position': position,
        'modules': {module.id: {'completed': False, 'attempts': 2, 'reflection': SECRET, 'source': SECRET}, 'unknown': {'reflection': SECRET}},
    }})
    selected = {'review_attempt_id': '1' * 32, 'scenario_attempt_id': '2' * 32}
    outcome = package_outcomes(package).modules[0].outcomes[0]
    validation, validation_hash = encode({'passed': False, 'checks': [{'id': outcome.id, 'passed': False, 'detail': SECRET},
                                                     {'id': 'unknown-private-check', 'passed': False, 'detail': SECRET}], 'source': SECRET})
    selection, selection_hash = encode(selected)
    row = await record(repo, enrollment, package, state='rejected', validation_json=validation, validation_sha256=validation_hash,
                       assessment_selection_json=selection, assessment_selection_sha256=selection_hash)
    await record(repo, enrollment, package, user_id='other-learner')
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    assert SECRET not in response.text and 'unknown-private-check' not in response.text
    result = response.json()
    assert result['modules'] == {module.id: {'completed': False, 'attempts': 2}}
    summary = result['support_summary']
    assert summary['read_only'] is True and summary['position_status'] == 'saved'
    assert summary['last_saved_lesson']['lesson_title'] == lesson['title']
    assert summary['last_saved_lesson']['revision'] == lesson['revision']
    assert summary['pending_completions'] == []
    assert len(summary['recent_completions']) == 1
    recent = summary['recent_completions'][0]
    assert recent['attempt_id'] == row['uuid'] and recent['selected_evidence'] == selected
    assert recent['failed_required_outcomes'] == [{'outcome_id': outcome.id, 'statement': outcome.statement}]
    assert await snapshot(repo) == before


@pytest.mark.parametrize('changed', [dict(revision=True), dict(revision=999), dict(content_sha256='bad'), dict(module_id=[]), dict(lesson_id='absent')])
async def test_invalid_reading_position_is_not_inferred(repo, monkeypatch, tmp_path, changed):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    module = package.manifest.modules[0]
    lesson = package.json('lessons.json')[module.id]['lessons'][0]
    position = dict(module_id=module.id, lesson_id=lesson['id'], revision=lesson['revision'], content_sha256=hashlib.sha256(lesson['content'].encode()).hexdigest())
    position.update(changed)
    await repo.progress.update_one({'user_id': enrollment.user_id}, {'$set': {'learning_position': position}})
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    assert response.json()['support_summary']['position_status'] == 'unavailable'
    assert response.json()['support_summary']['last_saved_lesson'] is None


@pytest.mark.parametrize('changed', [dict(uuid=12), dict(manifest_sha256='changed'), dict(rubric_id='changed'),
    dict(assessment_selection_json='{}', assessment_selection_sha256='wrong'),
    dict(result_json='{}', result_sha256='wrong'),
    dict(result_json=encode({'attempt_id': 'wrong'})[0], result_sha256=encode({'attempt_id': 'wrong'})[1]),
    dict(validation_json='{}', validation_sha256=hashlib.sha256(b'{}').hexdigest())])
async def test_corrupt_history_is_unavailable_without_invented_feedback(repo, monkeypatch, tmp_path, changed):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    await record(repo, enrollment, package, **changed)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    recent = response.json()['support_summary']['recent_completions']
    assert len(recent) == 1 and recent[0]['state'] == 'unavailable'
    assert 'attempt_id' not in recent[0] and SECRET not in response.text


async def test_recent_history_is_bounded_sorted_and_does_not_read_another_enrollment(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    for index in range(12):
        await record(repo, enrollment, package, uuid=f'{index:032x}', created_at=datetime.datetime(2026, 10, 1, 0, index))
    await record(repo, enrollment, package, enrollment_id='unrelated', state='evaluating')
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    summary = response.json()['support_summary']
    assert summary['older_completions_available'] is True and summary['pending_completions'] == []
    assert [row['attempt_id'] for row in summary['recent_completions']] == [f'{index:032x}' for index in range(11, 1, -1)]
    assert await snapshot(repo) == before


async def test_pending_grade_detects_changed_answers_and_does_not_recover(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    await record(repo, enrollment, package, state='graded')
    await repo.progress.update_one({'user_id': enrollment.user_id}, {'$set': {'modules': {'ai_literacy': {'reflection': SECRET}}}})
    await repo.selections.update_one({'user_id': enrollment.user_id}, {'$set': {'in_flight_writes': 1}})
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    summary = response.json()['support_summary']
    assert summary['pending_completions'][0]['in_flight'] is True
    assert 'changed after grading' in summary['recent_completions'][0]['next_step']
    assert await snapshot(repo) == before


async def test_staff_read_is_allowed_but_learner_read_is_forbidden_and_owner_binding_checked(repo, monkeypatch, tmp_path):
    enrollment, _, app, client = await setup(repo, monkeypatch, tmp_path)
    before = await snapshot(repo)
    async with client:
        response = await client.get('/admin/certifications/someone-else', params={'enrollment_id': enrollment.uuid})
        assert response.status_code == 409
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=enrollment.user_id, is_admin=False, is_staff=False)
        assert (await read(client, enrollment)).status_code == 403
    assert await snapshot(repo) == before


async def test_unbound_legacy_progress_is_not_enrolled_and_private_fields_are_removed(repo, monkeypatch):
    await CertificationProgress(user_id='historical', modules={'ai_literacy': {'completed': True, 'stars': True, 'attempts': -1, 'reflection': SECRET}}).insert()
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='operator', is_admin=True, is_staff=False)
    before = await snapshot(repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/admin/certifications/historical')
    assert response.status_code == 200, response.text
    assert response.json()['modules'] == {'ai_literacy': {'completed': True}}
    assert 'Historical course version is unknown' in response.json()['support_summary']['explanation']
    assert await snapshot(repo) == before


async def test_old_course_does_not_inherit_another_selected_courses_worker(repo, monkeypatch, tmp_path):
    from app.models.certification import CertificationEnrollment
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    await record(repo, enrollment, package, state='evaluating')
    other_id = uuid4().hex
    other_progress = CertificationProgress(user_id=enrollment.user_id, enrollment_id=other_id, course_version=enrollment.course_version)
    await other_progress.insert()
    await CertificationEnrollment(uuid=other_id, user_id=enrollment.user_id, course_version=enrollment.course_version,
        manifest_sha256=package.manifest_sha256, progress_id=str(other_progress.id), provenance='explicit_upgrade').insert()
    await repo.selections.update_one({'user_id': enrollment.user_id}, {'$set': {'active_enrollment_id': other_id, 'in_flight_writes': 1}})
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    assert response.json()['is_active'] is False
    assert response.json()['support_summary']['pending_completions'][0]['in_flight'] is False
    assert response.json()['support_summary']['operations']['worker_marked_in_flight'] is False
    assert await snapshot(repo) == before


async def test_ambiguous_pending_requests_are_not_offered_as_a_single_retry(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    for _ in range(2):
        await record(repo, enrollment, package, state='evaluating')
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    pending = response.json()['support_summary']['pending_completions']
    assert len(pending) == 2 and all(row['state'] == 'review' for row in pending)
    assert all('Multiple unfinished requests' in row['next_step'] for row in pending)


async def test_corrupt_pending_course_is_conflict_and_never_recovered_on_read(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    await record(repo, enrollment, package, state='evaluating', manifest_sha256='wrong')
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 409
    assert await snapshot(repo) == before


@pytest.mark.parametrize('passing', [True, False])
async def test_support_reads_actual_selected_completion_and_rejects_changed_terminal_result(repo, monkeypatch, passing):
    from tests.integration import test_certification_outcome_completion as completion
    f, client, _, body, failed, judge = await completion.setup(repo, monkeypatch)
    if not passing:
        body['scenario_attempt_id'] = failed
    request_id = uuid4().hex
    async with client:
        response = await client.post('/certification/modules/validation_qa/complete',
            params={'enrollment_id': f.learner.uuid, 'request_id': request_id}, json=body)
        assert response.status_code == (200 if passing else 400), response.text
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    app = FastAPI()
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id='operator', is_admin=False, is_staff=True)
    before = await snapshot(repo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as support:
        response = await read(support, f.learner)
        assert response.status_code == 200, response.text
        entry = response.json()['support_summary']['recent_completions'][0]
        assert entry['attempt_id'] == request_id and entry['state'] == ('applied' if passing else 'rejected')
        assert bool(entry['failed_required_outcomes']) is not passing
        assert await snapshot(repo) == before
        rows = AttemptRepository().records
        raw = await rows.find_one({'uuid': request_id})
        result = json.loads(raw['result_json'])
        result['validation']['passed'] = not passing
        serialized, digest = encode(result)
        await rows.update_one({'uuid': request_id}, {'$set': {'result_json': serialized, 'result_sha256': digest}})
        response = await read(support, f.learner)
        entry = response.json()['support_summary']['recent_completions'][0]
        assert entry['state'] == 'unavailable' and 'attempt_id' not in entry
    judge.assert_awaited_once()


async def test_damaged_pending_grade_is_not_presented_as_a_safe_recovery(repo, monkeypatch, tmp_path):
    enrollment, package, _, client = await setup(repo, monkeypatch, tmp_path)
    await record(repo, enrollment, package, state='graded', validation_json=None, validation_sha256=None)
    before = await snapshot(repo)
    async with client:
        response = await read(client, enrollment)
    assert response.status_code == 200, response.text
    pending = response.json()['support_summary']['pending_completions'][0]
    assert pending['state'] == 'review' and 'no saved grade or safe retry is inferred' in pending['next_step']
    assert await snapshot(repo) == before
