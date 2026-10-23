"""Loopback-only saved-outcome QA using disposable MongoDB and synthetic judges."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import uvicorn
from bson import json_util
from fastapi import FastAPI

from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import course_history, module_readiness, practical_history, review_delivery, runtime, scenario_history, upgrade_comparison, validation_delivery
from app.services.certification_versions.scenario_submissions import module_bank
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_reviews as validation


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only the disposable loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-outcome-selection-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            completion = os.environ.get('CERTIFICATION_QA_COMPLETION') == '1'
            if completion:
                from tests.integration import test_certification_outcome_rubric as grading
                fixture, review_id, failed, passed, judge = await grading.fixture(repository, patches, single_module=True)
                patches.setattr('app.services.certification_service._fire_certification_complete_hooks', AsyncMock())
            else:
                fixture = await validation.fixture(repository)
            if not completion:
                saved = await validation.submit(repository, fixture)
                prepared = await validation.prepare(repository, fixture, saved['uuid'])
                judge = AsyncMock(side_effect=base.supported_review)
                await base.evaluate_review(repository, fixture.learner, fixture.package, prepared['attempt_id'], judge)
                bank = module_bank(fixture.package, 'validation_qa')
                failed, passed = uuid4().hex, uuid4().hex
                await base.submit_scenario(repository, fixture.learner, fixture.package, bank, {}, failed)
                await base.submit_scenario(repository, fixture.learner, fixture.package, bank,
                    {question.id: question.correct_choice_id for question in bank.questions}, passed)
                review_id = prepared['attempt_id']
            for module in (runtime, practical_history, upgrade_comparison, scenario_history, module_readiness,
                           review_delivery, validation_delivery, course_history):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            patches.setattr(validation_delivery, 'get_storage', lambda: fixture.storage)
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=fixture.learner.user_id)
            database = repository.enrollments.database
            assert database.name.startswith('certification_qa_')

            @app.get('/qa/state')
            async def state():
                digest = hashlib.sha256()
                counts = {}
                for name in sorted(await database.list_collection_names()):
                    rows = await database[name].find({}).sort('_id', 1).to_list(None)
                    counts[name] = len(rows)
                    digest.update(name.encode())
                    digest.update(json_util.dumps(rows, sort_keys=True).encode())
                return {'database': database.name, 'database_sha256': digest.hexdigest(),
                        'counts': counts, 'judge_calls': judge.await_count,
                        'progress': (await repository.read_progress(fixture.learner.user_id, fixture.learner.uuid)).model_dump(mode='json') if completion else None,
                        'credentials': await database['certification_credentials'].count_documents({}) if completion else None}

            output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'database': database.name,
                'module_id': 'validation_qa', 'enrollment_id': fixture.learner.uuid,
                'review_id': review_id, 'completion_enabled': completion, 'failed_scenario_id': failed, 'passed_scenario_id': passed}))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

            @app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable outcome selection database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
