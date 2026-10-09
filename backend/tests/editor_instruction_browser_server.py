"""Disposable instruction editor + certification HTTP QA. Synthetic models only."""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import uvicorn

from app.dependencies import get_current_user
from app.models.user import User
from app.models.search_set import SearchSetItem
from app.routers.certification import router as certification_router
from app.routers.extractions import router as extraction_router
from app.services.certification_versions import validation_delivery
from app.services.certification_versions.attempts import encode
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_http as http
from tests.integration import test_certification_validation_suites as suites

WRONG = 'Extract the Year 1 total instead of the complete project budget.'

async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27029':
        raise RuntimeError('Only isolated QA MongoDB on 27029 is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION']).resolve()
    if not str(output).startswith('/private/tmp/'):
        raise RuntimeError('Session output must be under /private/tmp')
    with TemporaryDirectory(prefix='certification-editor-browser-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repo = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            base.versioned_runtime.__wrapped__(repo, patches)
            f = await http.fixture(repo, patches)
            user = User(user_id=f.learner.user_id)
            f.app.dependency_overrides[get_current_user] = lambda: user
            f.app.include_router(certification_router, prefix='/api/certification')
            f.app.include_router(extraction_router, prefix='/api/extractions')
            f.fields[1].searchphrase = WRONG
            await f.fields[1].save()
            params = {'enrollment_id': f.learner.uuid}
            inputs = validation_delivery.ValidationInputRepository()
            async with f.client as client:
                captured = await http.post(client, 'modules/validation_qa/validation-captures', params, f.body)
                saved = await inputs.get(user.user_id, captured['uuid'])
                original_hash = encode(saved)[1]
                suite = await http.post(client, 'modules/validation_qa/validation-suites', params, suites.request(f, saved))
                original = await http.plan_and_run(f, client, params, captured, suite)
                assert original['result']['checks']['observed_semantic_failure']
                listing = await client.get('/certification/modules/validation_qa/validation-suites', params=params)
                assert listing.status_code == 200, listing.text
            database = repo.enrollments.database.name
            assert database.startswith('certification_qa_')
            session = {'api_origin': 'http://127.0.0.1:5310', 'database': database,
                'listing': listing.json(), 'original': original, 'field_id': str(f.fields[1].id),
                'wrong_instruction': WRONG, 'initial_provider_calls': f.provider.call_count}
            output.write_text(json.dumps(session, indent=2) + '\n')

            @f.app.post('/qa/reset-instruction')
            async def reset_instruction():
                field = await SearchSetItem.get(f.fields[1].id)
                field.searchphrase = WRONG
                await field.save()
                return {'disposable_fixture_reset': True}

            @f.app.get('/qa/state')
            async def state():
                progress = await repo.read_progress(user.user_id, f.learner.uuid)
                field = await SearchSetItem.get(f.fields[1].id)
                return {'database': database, 'field_id': str(field.id), 'title': field.title,
                    'instruction': field.searchphrase, 'total_xp': progress.total_xp, 'certified': progress.certified,
                    'original_capture_unchanged': encode(await inputs.get(user.user_id, captured['uuid']))[1] == original_hash,
                    'provider_calls': f.provider.call_count, 'judge_calls': f.judge.await_count}

            server = uvicorn.Server(uvicorn.Config(f.app, host='127.0.0.1', port=5310, log_level='warning'))

            @f.app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable editor QA database removed', flush=True)

if __name__ == '__main__':
    asyncio.run(main())
