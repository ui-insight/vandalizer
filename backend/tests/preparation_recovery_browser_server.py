"""Loopback-only learner recovery against a genuinely paused synthetic worker."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import FastAPI
import pytest
import uvicorn

from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import course_history, runtime, selection_delivery, selection_preparation_recovery, upgrade_comparison
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_selection_preparation_recovery as core
from tests.integration.test_certification_saved_course_selection import histories


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only disposable loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-preparation-recovery-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            async with core.worker(repository, patches, phase='before_cas') as (user, current, request, journal, action, task, release):
                for module in (runtime, selection_delivery, selection_preparation_recovery, upgrade_comparison, course_history):
                    patches.setattr(module, 'EnrollmentRepository', lambda: repository)
                patches.setattr(runtime, 'versioning_enabled', lambda: True)
                fail_next = {'enabled': True}
                finish = core.SelectionPreparationRecovery.finish
                async def interrupted(self, raw, intent):
                    if fail_next['enabled']:
                        fail_next['enabled'] = False
                        raise EnrollmentConflict('Synthetic interruption after recovery claimed preparation')
                    return await finish(self, raw, intent)
                patches.setattr(core.SelectionPreparationRecovery, 'finish', interrupted)
                app = FastAPI()
                app.include_router(router, prefix='/api/certification')
                app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user)
                database = repository.enrollments.database
                assert database.name.startswith('certification_qa_')
                outcome = {'late_worker_rejected': False}

                @app.get('/qa/state')
                async def state():
                    history = json.dumps(await histories(repository, user), default=str, sort_keys=True)
                    selection = await repository.selections.find_one({'user_id': user})
                    return {'database': database.name, 'history_sha256': hashlib.sha256(history.encode()).hexdigest(),
                            'active_enrollment_id': selection['active_enrollment_id'], 'revision': selection['revision'],
                            'in_flight_writes': selection['in_flight_writes'],
                            'recovery_records': await core.SelectionPreparationRecovery(repository).records.count_documents({}), **outcome}

                @app.post('/qa/resume-old-worker')
                async def resume_old_worker():
                    release.set()
                    result = (await asyncio.gather(task, return_exceptions=True))[0]
                    outcome['late_worker_rejected'] = isinstance(result, EnrollmentConflict)
                    return await state()

                output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'database': database.name}))
                server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

                @app.post('/qa/shutdown')
                async def shutdown():
                    server.should_exit = True
                    return {'disposable_fixture_stopping': True}

                await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable preparation-recovery database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
