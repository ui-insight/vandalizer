"""Disposable learner choice delivery; synthetic credit, no production data or sends."""
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
from app.routers import certification_upgrades
from app.services.certification_versions import course_history, runtime, selection_delivery, upgrade_comparison, upgrade_delivery
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_upgrade_decisions as choices
from tests.integration.test_certification_saved_course_selection import histories


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only disposable loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-upgrade-choice-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            source, target, _, _ = await choices.setup(repository)
            progress = await repository.read_progress(source.user_id, source.uuid)
            progress.total_xp = 125
            progress.modules = {'foundations': {'completed': True, 'stars': 2, 'xp_earned': 125,
                'completed_at': '2026-09-01', 'self_assessment': {'original': 'retained reflection'},
                'provisioned_docs': ['original-lab-document']},
                'ai-literacy': {'completed': False, 'self_assessment': {'draft': 'Keep this unfinished answer'}}}
            progress.lab_folder_id = 'original-course-folder'
            progress.learning_position = {'module_id': 'foundations', 'lesson_id': 'original-place'}
            await progress.save()
            for module in (runtime, selection_delivery, upgrade_comparison, course_history, upgrade_delivery):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            patches.setattr(certification_upgrades, 'versioning_enabled', lambda: True)
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=source.user_id)
            database = repository.enrollments.database
            assert database.name.startswith('certification_qa_')

            @app.get('/qa/state')
            async def state():
                data = await histories(repository, source.user_id)
                selection = await repository.selections.find_one({'user_id': source.user_id})
                progress_rows = await repository.progress.find({'user_id': source.user_id}).to_list(None)
                source_data = {'enrollments': [row for row in data['enrollments'] if row['uuid'] == source.uuid],
                    'progress': [row for row in data['progress'] if str(row['_id']) == source.progress_id]}
                return {'database': database.name, 'source_id': source.uuid, 'target_version': target,
                    'source_sha256': hashlib.sha256(json.dumps(source_data, default=str, sort_keys=True).encode()).hexdigest(),
                    'history_sha256': hashlib.sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest(),
                    'selection': {key: selection.get(key) for key in ('active_enrollment_id', 'revision', 'pending_transition_id')},
                    'xp': sorted(row['total_xp'] for row in progress_rows),
                    'enrollments': await repository.enrollments.count_documents({}),
                    'decisions': await database['certification_upgrade_decisions'].count_documents({}),
                    'activations': await database['certification_upgrade_activations'].count_documents({}),
                    'saved_selections': await database['certification_saved_course_selections'].count_documents({})}

            output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'database': database.name,
                'source_id': source.uuid, 'target_version': target}))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

            @app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable upgrade-choice database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
