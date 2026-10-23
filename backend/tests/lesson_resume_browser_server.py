"""Disposable real-persistence server for cross-browser lesson cursor QA.

Only the explicit loopback test MongoDB is used. The copied registry and test
identity are disposable; no model, publication or real learner is involved.
"""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
import uvicorn
from fastapi import FastAPI

from tests.integration import test_certification_enrollments as base
from app.dependencies import get_current_user
from app.models.certification import CertificationCredential, CertificationAttempt
from app.routers.certification import router
from app.services import chat_tools
from app.services.certification_versions import runtime


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only the isolated loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-lesson-resume-browser-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            patches.setattr(runtime, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            user_id = 'qa-lesson-resume-reader'
            source = await repository.ensure_initial(user_id)
            progress = await repository.read_progress(user_id, source.uuid)
            progress.modules = {
                'foundations': {'completed': True, 'stars': 2, 'xp_earned': 100, 'attempts': 1},
                'ai_literacy': {'self_assessment': {'experience': 'A preserved synthetic answer'}, 'provisioned_docs': ['qa-preserved-document']},
            }
            progress.total_xp = 100
            await progress.save()
            context = SimpleNamespace(deps=SimpleNamespace(user_id=user_id))
            lesson = await chat_tools.get_certification_lesson(context, 'ai_literacy', 1, enrollment_id=source.uuid)
            module = await chat_tools.get_certification_module(context, 'ai_literacy')
            database = repository.enrollments.database.name
            assert database.startswith('certification_qa_')
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=user_id)

            @app.get('/qa/state')
            async def state():
                saved = await repository.read_progress(user_id, source.uuid)
                selection = await repository.selections.find_one({'user_id': user_id})
                return {'database': database, 'enrollment_id': source.uuid,
                    'active_enrollment_id': selection['active_enrollment_id'],
                    'in_flight_writes': selection.get('in_flight_writes', 0),
                    'total_xp': saved.total_xp, 'certified': saved.certified,
                    'modules': saved.modules, 'learning_position': saved.learning_position,
                    'position_revision': saved.position_revision,
                    'credentials': await CertificationCredential.get_motor_collection().count_documents({}),
                    'attempts': await CertificationAttempt.get_motor_collection().count_documents({})}

            output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'database': database,
                'enrollment_id': source.uuid, 'lesson': lesson, 'module': module}))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

            @app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable lesson resume QA database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
