"""Isolated stopped-run browser fixture; actual engine with synthetic providers."""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import uvicorn
from fastapi import FastAPI

from tests.integration import test_certification_enrollments as base
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision, CertificationReviewAttempt, CertificationCredential
from app.routers.certification import router
from app.services.certification_versions import runtime, practical_history, upgrade_comparison, scenario_history


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only the isolated loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-connected-recovery-browser-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            data, client, fixture_app, judge, _, providers = await base.connected_http_fixture(repository, patches)
            await client.aclose()
            source, package, _, workflow = data[:4]
            for module in (runtime, practical_history, upgrade_comparison, scenario_history):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides.update(fixture_app.dependency_overrides)
            database = repository.enrollments.database.name
            assert database.startswith('certification_qa_')

            @app.get('/qa/state')
            async def state():
                progress = await repository.read_progress(source.user_id, source.uuid)
                selection = await repository.selections.find_one({'user_id': source.user_id})
                counts = {}
                for name, model in [('captures', CertificationLabInput), ('runs', CertificationLabExecution),
                        ('decisions', CertificationLearnerDecision), ('reviews', CertificationReviewAttempt), ('credentials', CertificationCredential)]:
                    counts[name] = await model.get_motor_collection().count_documents({})
                return {**counts, 'database': database, 'enrollment_id': source.uuid,
                    'active_enrollment_id': selection['active_enrollment_id'], 'selection_revision': selection['revision'],
                    'in_flight_writes': selection.get('in_flight_writes', 0), 'total_xp': progress.total_xp,
                    'certified': progress.certified, 'provider_calls': [provider.call_count for provider in providers], 'judge_calls': judge.await_count}

            output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'module_id': 'multi_step',
                'enrollment_id': source.uuid, 'workflow_id': str(workflow.id), 'database': database,
                'case': package.json('connected-cases/multi_step.json')}))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

            @app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable connected recovery QA database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
