"""Disposable loopback committed-selection recovery; no real accounts or sends."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
import pytest
import uvicorn

from app.dependencies import get_current_user
from app.routers.certification import router
from app.services.certification_versions import course_history, runtime, selection_delivery, upgrade_comparison
from app.services.certification_versions.saved_course_selection import SavedCourseSelectionRepository
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_upgrade_activation as activation
from tests.integration.test_certification_saved_course_selection import histories


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only disposable loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-selection-recovery-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            source, request, journal, _ = await activation.setup(repository, certified=True)
            staged_mode = os.environ.get('CERTIFICATION_QA_STAGED') == '1'
            async def interrupted(*args):
                raise RuntimeError('Synthetic lost confirmation')
            if staged_mode:
                await journal.targets.prepare(source.user_id, request['decision_id'])
            else:
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(journal, 'finalize', interrupted)
                    try:
                        await journal.activate(source.user_id, request)
                    except RuntimeError as exc:
                        assert str(exc) == 'Synthetic lost confirmation'
            for module in (runtime, selection_delivery, upgrade_comparison, course_history):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
            database = repository.enrollments.database
            assert database.name.startswith('certification_qa_')

            @app.get('/qa/state')
            async def state():
                data = await histories(repository, source.user_id)
                lifecycle = {row['uuid']: row.pop('state') for row in data['enrollments']}
                history = json.dumps(data, default=str, sort_keys=True)
                selection = await repository.selections.find_one({'user_id': source.user_id})
                return {'database': database.name, 'history_sha256': hashlib.sha256(history.encode()).hexdigest(),
                        'selection': {key: selection.get(key) for key in ('active_enrollment_id', 'revision', 'pending_transition_id')},
                        'enrollments': await repository.enrollments.count_documents({}),
                        'lifecycle': lifecycle,
                        'credentials': await database['certification_credentials'].count_documents({})}

            @app.post('/qa/commit-prepared')
            async def commit_prepared():
                assert staged_mode
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(journal, 'clear_pending', interrupted)
                    try:
                        await journal.activate(source.user_id, request)
                    except RuntimeError as exc:
                        assert str(exc) == 'Synthetic lost confirmation'
                return await state()

            @app.post('/qa/next/{action}')
            async def next_choice(action: str):
                assert action in ('return_to_original_course', 'resume_upgraded_course')
                service = SavedCourseSelectionRepository(repository)
                preview = await service.preview(source.user_id, request['request_id'], action)
                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(service, 'finalize', interrupted)
                    try:
                        await service.select(source.user_id, {'request_id': uuid4().hex, 'activation_id': request['request_id'],
                            'action': action, 'preview_sha256': preview['preview_sha256'],
                            'consent': 'select_saved_course_preserving_both_histories_and_credit'})
                    except RuntimeError as exc:
                        assert str(exc) == 'Synthetic lost confirmation'
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
            print('Disposable selection-recovery database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
