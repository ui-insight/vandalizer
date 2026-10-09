"""Disposable loopback-only Governance browser QA; never application data.

Run from backend with CERTIFICATION_TEST_MONGO_URL=mongodb://127.0.0.1:27028
and CERTIFICATION_QA_SESSION pointing to a temporary session JSON file.
The authored source expectations substitute model dispatch for deterministic QA;
this does not establish live-model or causal learner-grading accuracy.
"""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest
import uvicorn
from fastapi import FastAPI

from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_governance_http as http
from app.models.certification import CertificationLabInput, CertificationLabExecution, CertificationLearnerDecision, CertificationReviewAttempt, CertificationCredential
from app.routers.certification import router
from app.services.extraction_engine import ExtractionEngine
from app.services.certification_versions import runtime, practical_history, upgrade_comparison, scenario_history


async def main():
    if os.environ.get('CERTIFICATION_TEST_MONGO_URL') != 'mongodb://127.0.0.1:27028':
        raise RuntimeError('Only the explicitly isolated loopback MongoDB is allowed')
    output = Path(os.environ['CERTIFICATION_QA_SESSION'])
    if not str(output.resolve()).startswith(('/private/tmp/', '/tmp/')):
        raise RuntimeError('Use a disposable session file under /tmp')
    with TemporaryDirectory(prefix='certification-governance-browser-') as folder:
        generator = base.repo.__wrapped__(Path(folder))
        repository = await anext(generator)
        patches = pytest.MonkeyPatch()
        try:
            real_extract = ExtractionEngine.extract
            f = await http.fixture(repository, patches)
            await f.client.aclose()
            patches.setattr(ExtractionEngine, 'extract', real_extract)
            for module in (runtime, practical_history, upgrade_comparison, scenario_history):
                patches.setattr(module, 'EnrollmentRepository', lambda: repository)
            patches.setattr(runtime, 'versioning_enabled', lambda: True)
            f.fields[3].searchphrase = 'Return the Approved Project Ceiling as the currently obligated amount. This is the disclosed original diagnostic flaw.'
            await f.fields[3].save()
            def dispatch(content, keys, model, config, meta_map, capture_sources):
                assert 'RSP-2026-042' in content and 'issued amendment' in content.lower()
                assert len(keys) == 6 and capture_sources is True
                values = {e.field: e.expected_value for e in f.case.expectations}
                if 'original diagnostic flaw' in keys[3]:
                    values['Funds Obligated to Date'] = '600000'
                return [{key: values[field.title] for key, field in zip(keys, f.case.fields)}]
            provider = Mock(side_effect=dispatch)
            patches.setattr(ExtractionEngine, '_dispatch_extraction', provider)
            app = FastAPI()
            app.include_router(router, prefix='/api/certification')
            app.dependency_overrides.update(f.app.dependency_overrides)
            database = repository.enrollments.database.name
            assert database.startswith('certification_qa_')

            @app.get('/qa/state')
            async def state():
                progress = await repository.read_progress(f.learner.user_id, f.learner.uuid)
                selection = await repository.selections.find_one({'user_id': f.learner.user_id})
                counts = {}
                for name, model in [('captures', CertificationLabInput), ('runs', CertificationLabExecution),
                        ('decisions', CertificationLearnerDecision), ('reviews', CertificationReviewAttempt), ('credentials', CertificationCredential)]:
                    counts[name] = await model.get_motor_collection().count_documents({})
                return {**counts, 'database': database, 'enrollment_id': f.learner.uuid,
                    'active_enrollment_id': selection['active_enrollment_id'], 'selection_revision': selection['revision'],
                    'in_flight_writes': selection.get('in_flight_writes', 0), 'total_xp': progress.total_xp,
                    'certified': progress.certified, 'extraction_calls': provider.call_count, 'judge_calls': f.judge.await_count}

            @app.post('/qa/repair')
            async def repair_owned_training_instruction():
                # Explicit synthetic editor substitute, not agentic-editor QA.
                f.fields[3].searchphrase = 'Return cumulative funds actually obligated under the latest issued amendment in USD; never the approved ceiling or the additional increment alone.'
                await f.fields[3].save()
                return {'synthetic_owned_field_repaired': True, 'artifact_id': f.artifact.uuid}

            output.write_text(json.dumps({'api_origin': 'http://127.0.0.1:5293', 'module_id': 'governance',
                'enrollment_id': f.learner.uuid, 'artifact_id': f.artifact.uuid, 'case_sha256': f.case.digest, 'database': database}))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=5293, log_level='warning'))

            @app.post('/qa/shutdown')
            async def shutdown():
                server.should_exit = True
                return {'disposable_fixture_stopping': True}

            await server.serve()
        finally:
            patches.undo()
            await generator.aclose()
            print('Disposable Governance QA database removed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
