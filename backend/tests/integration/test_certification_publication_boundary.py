"""Publication must not redirect an already accepted assessment or practical job.

Only the disposable catalog and MongoDB supplied by the shared fixture change.
Provider results are synthetic; these tests do not calibrate a reviewer.
"""
import asyncio
import hashlib
import json
import shutil
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.certification import CertificationAttempt, CertificationCredential
from app.services.certification_versions.attempts import AttemptRepository
from app.services.certification_versions.runtime import current_operation
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
worker_tasks = base.worker_tasks
pytestmark = base.pytestmark


def publish_successor(repository, version):
    """Use different teaching/exercise bytes and retire only new enrollment."""
    successor = 'publication-boundary-successor'
    directory = repository.catalog.root / successor
    shutil.copytree(repository.catalog.root / version, directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest['release_id'] = successor
    lessons = json.loads((directory / 'lessons.json').read_text())
    panel = json.loads((directory / 'panel-modules.json').read_text())
    module = panel[0]['id']
    for lesson in (lessons[module]['lessons'][0], panel[0]['lessons'][0]):
        lesson['content'] += '\nSynthetic successor teaching; applies only to this next course.'
        lesson['revision'] += 1
    exercises = json.loads((directory / 'exercises.json').read_text())
    exercises[module]['publication_boundary_note'] = 'Changed exercise in the next test course.'
    for filename, value in [('lessons.json', lessons), ('panel-modules.json', panel), ('exercises.json', exercises)]:
        (directory / filename).write_text(json.dumps(value))
        manifest['artifacts'][filename] = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    path = repository.catalog.root / 'registry.json'
    registry = json.loads(path.read_text())
    registry['releases'][successor] = dict(state='published', supported_for_existing=True,
        manifest_sha256=hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest())
    registry['new_enrollment_default'] = successor
    registry['releases'][version].update(state='retired', supported_for_existing=True)
    path.write_text(json.dumps(registry))
    return repository.catalog.load(successor, new_enrollment=True)


@pytest.mark.parametrize('pause_after_grade', [False, True])
async def test_completion_keeps_original_rules_during_publication(versioned_runtime, monkeypatch, worker_tasks, pause_after_grade):
    from app.services import certification_service as service

    repository = versioned_runtime
    source = await repository.ensure_initial('publication-completion')
    package = repository.catalog.load(source.course_version)
    await service.store_assessment(source.user_id, 'ai_literacy',
        {'experience': 'Some', 'comfort': 'Some', 'concern': 'Some'}, enrollment_id=source.uuid)
    entered, resume = asyncio.Event(), asyncio.Event()
    original = service.validate_module
    seen = []

    async def paused_grade(*args, **kwargs):
        operation = current_operation()
        seen.append(operation.package)
        result = await original(*args, **kwargs) if pause_after_grade else None
        entered.set()
        await resume.wait()
        assert current_operation().package is operation.package
        return result if pause_after_grade else await original(*args, **kwargs)

    grader = AsyncMock(side_effect=paused_grade)
    monkeypatch.setattr(service, 'validate_module', grader)
    request_id = uuid4().hex
    task = worker_tasks(service.complete_module(source.user_id, 'ai_literacy',
        enrollment_id=source.uuid, request_id=request_id))
    await asyncio.wait_for(entered.wait(), 10)
    attempt_before = await AttemptRepository().records.find_one({'uuid': request_id})
    assert attempt_before['state'] == 'evaluating'
    successor = publish_successor(repository, source.course_version)
    assert successor.manifest.artifacts['lessons.json'] != package.manifest.artifacts['lessons.json']
    assert successor.manifest.artifacts['exercises.json'] != package.manifest.artifacts['exercises.json']
    assert (await repository.ensure_initial('publication-new-learner')).course_version == successor.manifest.release_id
    assert (await repository.current(source.user_id)).uuid == source.uuid
    resume.set()
    result = await asyncio.wait_for(task, 10)
    assert result['course_version'] == source.course_version
    assert result['xp_earned'] > 0
    assert seen[0].manifest_bytes == package.manifest_bytes
    saved = await AttemptRepository().records.find_one({'uuid': request_id})
    for field in ('course_version', 'manifest_sha256', 'rubric_id', 'artifact_sha256', 'progress_json', 'progress_sha256'):
        assert saved[field] == attempt_before[field]
    assert saved['artifact_sha256'] == package.manifest.artifacts
    grader.side_effect = AssertionError('Saved completion must replay without grading')
    assert await service.complete_module(source.user_id, 'ai_literacy', enrollment_id=source.uuid, request_id=request_id) == result
    assert grader.await_count == 1
    assert await CertificationAttempt.count() == 1
    assert (await repository.read_progress(source.user_id, source.uuid)).total_xp == result['xp_earned']
    assert current_operation() is None


async def test_practical_review_keeps_packet_and_receipt_during_publication(repo, monkeypatch, worker_tasks):
    source, package, _, run, _, payload, config, model, service = await base.assessment_delivery_fixture(repo, monkeypatch)
    entered, resume = asyncio.Event(), asyncio.Event()
    packets = []

    async def paused_model(name, settings, packet):
        packets.append(packet)
        entered.set()
        await resume.wait()
        return await base.supported_review(name, settings, packet)

    model.side_effect = paused_model
    task = worker_tasks(service.request(source.user_id, source.uuid, run['run_id'], payload))
    await asyncio.wait_for(entered.wait(), 10)
    original = await service.reviews.get(source.user_id, payload.request_id)
    assert original['state'] == 'evaluating'
    successor = publish_successor(repo, source.course_version)
    assert (await repo.ensure_initial('review-new-learner')).course_version == successor.manifest.release_id
    resume.set()
    result = await asyncio.wait_for(task, 10)
    saved = await service.reviews.get(source.user_id, payload.request_id)
    assert saved['record'] == original['record']
    assert saved['record']['manifest_sha256'] == package.manifest_sha256
    assert json.loads(packets[0])['evidence'] == original['record']['evidence']
    assert result['status'] == 'requirements_supported'
    assert result['credit_awarded'] is result['staff_review_required'] is False
    config.side_effect = AssertionError('Replay must not reload reviewer settings')
    assert await service.request(source.user_id, source.uuid, run['run_id'], payload) == result
    model.assert_awaited_once()
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0
    assert await CertificationCredential.count() == 0


async def test_practical_execution_keeps_original_plan_during_publication(repo, monkeypatch, worker_tasks):
    import threading
    from unittest.mock import Mock
    from app.services.extraction_engine import ExtractionEngine

    source, package, _, run, payload, config, service = await base.practical_execution_fixture(repo, monkeypatch)
    entered, resume = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    def paused_extract(**kwargs):
        loop.call_soon_threadsafe(entered.set)
        if not resume.wait(15):
            raise TimeoutError('Synthetic publication test did not release provider')
        return [{'Project title': 'Synthetic original-course result'}]

    provider = Mock(side_effect=paused_extract)
    monkeypatch.setattr(ExtractionEngine, 'extract', provider)
    task = worker_tasks(service.execute(source.user_id, source.uuid, run['run_id'], payload))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        executing = await service.runs.get(source.user_id, run['run_id'])
        assert executing['state'] == 'executing'
        successor = publish_successor(repo, source.course_version)
        assert (await repo.ensure_initial('execution-new-learner')).course_version == successor.manifest.release_id
    finally:
        resume.set()
    result = await asyncio.wait_for(task, 10)
    assert result['state'] == 'completed'
    assert result['course_version'] == source.course_version
    assert result['manifest_sha256'] == package.manifest_sha256
    saved = await service.runs.get(source.user_id, run['run_id'])
    assert saved['plan'] == executing['plan'] == run['plan']
    assert saved['plan_sha256'] == run['plan_sha256']
    assert saved['authorization'] == executing['authorization']
    assert saved['result']['entities'] == [{'Project title': 'Synthetic original-course result'}]
    assert provider.call_args.kwargs['doc_texts'] == ['Synthetic ingestion text for the storage fixture.']
    config.side_effect = AssertionError('A replay must not load new execution settings')
    assert await service.execute(source.user_id, source.uuid, run['run_id'], payload) == result
    provider.assert_called_once()
    assert (await repo.current(source.user_id)).uuid == source.uuid
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0
    assert await CertificationCredential.count() == 0
