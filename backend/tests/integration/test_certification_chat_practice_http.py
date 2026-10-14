"""M00-02 over HTTP: the practice check reads the pinned package and writes nothing."""
import hashlib
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from app.models.certification import CertificationLabInput, CertificationScenarioAttempt
from app.services.certification_versions.catalog import CATALOG_ROOT
from tests.integration import test_certification_enrollments as base

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


def add_practice(repo, version):
    directory, draft = repo.catalog.root / version, CATALOG_ROOT.parent / 'drafts/v5.0'
    exercises = json.loads((directory / 'exercises.json').read_text())
    exercises['ai_literacy'] = json.loads((draft / 'ai-literacy-exercise.json').read_text())
    (directory / 'exercises.json').write_text(json.dumps(exercises))
    name = exercises['ai_literacy']['chat_practice']['document']
    shutil.copyfile(draft / 'documents' / name, directory / 'documents' / name)
    manifest = json.loads((directory / 'manifest.json').read_text())
    for path in ('exercises.json', 'documents/' + name):
        manifest['artifacts'][path] = hashlib.sha256((directory / path).read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    registry_path = repo.catalog.root / 'registry.json'
    registry = json.loads(registry_path.read_text())
    registry['releases'][version]['manifest_sha256'] = hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()
    registry_path.write_text(json.dumps(registry))


async def test_practice_check_uses_the_pinned_document_and_saves_nothing(versioned_runtime):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.dependencies import get_current_user
    from app.routers.certification import router
    repo = versioned_runtime
    version = base.add_scenario_fixture_course(repo)
    add_practice(repo, version)
    source = await repo.ensure_initial('practice-learner')
    app = FastAPI()
    app.include_router(router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
    path, params = '/certification/modules/ai_literacy/chat-practice-check', {'enrollment_id': source.uuid}
    honest = {'passage_quote': 'Requested Amount: $485,000', 'page': 1, 'value': '485000', 'unanswerable_judgment': 'not_stated_in_source'}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        done = await client.post(path, params=params, json=honest)
        assert done.status_code == 200, done.text
        assert done.json()['practice_complete'] is True and done.json()['saved'] is False
        accepted = await client.post(path, params=params, json={**honest, 'unanswerable_judgment': 'supported_by_source'})
        assert accepted.status_code == 200 and accepted.json()['judgment_correct'] is False
        assert 'states no rate' in ' '.join(accepted.json()['feedback'])
        exercise = await client.get('/certification/modules/ai_literacy/exercise', params=params)
        assert exercise.json()['documents'] == ['nsf-proposal-alpine-ecology.pdf'] and 'chat_practice' in exercise.json()
    progress = await repo.read_progress(source.user_id, source.uuid)
    assert progress.total_xp == 0 and not progress.modules.get('ai_literacy', {}).get('completed')
    assert await CertificationScenarioAttempt.get_motor_collection().count_documents({}) == 0
    assert await CertificationLabInput.get_motor_collection().count_documents({}) == 0
