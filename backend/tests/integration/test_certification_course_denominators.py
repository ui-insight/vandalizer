"""Synthetic cohorts verify adding modules never rewrites an older denominator."""
import datetime
import hashlib
import json
import shutil
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.routers import admin, certification
from app.services import chat_tools
from app.services.certification_versions import enrollments, readers, runtime
from app.services.certification_versions.catalog import CATALOG_ROOT
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = base.pytestmark


def version(repo, release_id, count):
    path = repo.catalog.root / release_id
    shutil.copytree(CATALOG_ROOT / base.VERSION, path)
    manifest = json.loads((path / 'manifest.json').read_text())
    manifest.update(release_id=release_id, title=f'Synthetic {count}-module course')
    manifest['modules'] = manifest['modules'][:count]
    ids = [module['id'] for module in manifest['modules']]
    for filename in ('lessons.json', 'exercises.json'):
        value = json.loads((path / filename).read_text())
        (path / filename).write_text(json.dumps({key: value[key] for key in ids}))
    panel = json.loads((path / 'panel-modules.json').read_text())
    (path / 'panel-modules.json').write_text(json.dumps([module for module in panel if module['id'] in ids]))
    structure = json.loads((path / 'course-structure.json').read_text())
    for tier in structure['tiers']:
        tier['moduleIds'] = [mid for mid in tier['moduleIds'] if mid in ids]
    structure['tiers'] = [tier for tier in structure['tiers'] if tier['moduleIds']]
    (path / 'course-structure.json').write_text(json.dumps(structure))
    for name in manifest['artifacts']:
        manifest['artifacts'][name] = hashlib.sha256((path / name).read_bytes()).hexdigest()
    (path / 'manifest.json').write_text(json.dumps(manifest))
    registry_path = repo.catalog.root / 'registry.json'
    registry = json.loads(registry_path.read_text())
    # Explicit isolated read-cohort fixture; not publication or grading evidence.
    registry['releases'][release_id] = {'state': 'published', 'supported_for_existing': True,
        'manifest_sha256': hashlib.sha256((path / 'manifest.json').read_bytes()).hexdigest()}
    registry['new_enrollment_default'] = release_id
    registry_path.write_text(json.dumps(registry))
    return repo.catalog.load(release_id)


async def seed(repo, user_id, package, completed, certified=False):
    learner = await repo.ensure_initial(user_id)
    ids = [module.id for module in package.manifest.modules]
    modules = {mid: {'completed': True, 'stars': 3, 'xp_earned': 100, 'attempts': 1} for mid in ids[:completed]}
    modules['unrelated_record'] = {'completed': True, 'stars': 3, 'xp_earned': 100}
    await repo.progress.update_one({'user_id': user_id}, {'$set': {'modules': modules, 'total_xp': 9999,
        'certified': certified, 'certified_at': datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc) if certified else None}})
    return learner


async def test_original_completed_and_active_courses_keep_their_denominators_when_default_adds_modules(repo, monkeypatch):
    source = version(repo, 'qa-three-module-source', 3)
    old_complete = await seed(repo, 'original-completed', source, 3, True)
    old_active = await seed(repo, 'original-active', source, 1)
    preserved = await repo.progress.find({'user_id': {'$in': [old_complete.user_id, old_active.user_id]}}).to_list(None)
    target = version(repo, 'qa-eleven-module-target', 11)
    new_active = await seed(repo, 'new-active', target, 1)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    monkeypatch.setattr(readers, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(enrollments, 'EnrollmentRepository', lambda: repo)
    actor = SimpleNamespace(user_id=old_complete.user_id, is_admin=False, is_staff=False)
    app = FastAPI()
    app.include_router(certification.router, prefix='/certification')
    app.include_router(admin.router, prefix='/admin')
    app.dependency_overrides[get_current_user] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for learner, package, completed, certified in ((old_complete, source, 3, True), (old_active, source, 1, False), (new_active, target, 1, False)):
            actor.user_id = learner.user_id
            response = await client.get('/certification/progress')
            assert response.status_code == 200, response.text
            progress = response.json()
            course = (await client.get('/certification/course', params={'enrollment_id': learner.uuid})).json()
            chat = await chat_tools.get_certification_progress(SimpleNamespace(deps=SimpleNamespace(user_id=learner.user_id)))
            ids = [module.id for module in package.manifest.modules]
            assert progress['module_ids'] == ids and course['module_ids'] == ids
            assert progress['modules_total'] == course['modules_total'] == chat['modules_total'] == len(ids)
            assert progress['maximum_xp'] == course['maximum_xp'] == package.summary()['maximum_xp']
            assert chat['modules_completed'] == completed and chat['certified'] is certified
            assert progress['certified'] is certified
            assert [row['module_id'] for row in chat['modules']] == ids
            assert len(course['modules']) == len(course['prerequisites']) == len(ids)
            assert set(course['prerequisites']) == set(ids)
            assert chat['next_module_id'] == (None if certified else ids[1])
            assert progress['enrollment_id'] == course['enrollment_id'] == chat['enrollment_id'] == learner.uuid
        actor.user_id, actor.is_staff = 'support', True
        response = await client.get('/admin/certifications')
        assert response.status_code == 200, response.text
        rows = {row['user_id']: row for row in response.json()['items']}
        assert (rows['original-completed']['modules_completed'], rows['original-completed']['modules_total'], rows['original-completed']['certified']) == (3, 3, True)
        assert (rows['original-active']['modules_completed'], rows['original-active']['modules_total']) == (1, 3)
        assert (rows['new-active']['modules_completed'], rows['new-active']['modules_total'], rows['new-active']['certified']) == (1, 11, False)
        detail = await client.get('/admin/certifications/original-completed', params={'enrollment_id': old_complete.uuid})
        assert detail.status_code == 200 and detail.json()['modules_total'] == 3
    assert await repo.progress.find({'user_id': {'$in': [old_complete.user_id, old_active.user_id]}}).to_list(None) == preserved
    assert (await repo.current('original-completed')).uuid == old_complete.uuid
