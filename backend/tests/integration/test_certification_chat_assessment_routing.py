"""Chat reads the pinned assessment route, never a legacy list of module names."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.routers import certification
from app.services import chat_tools, certification_service
from app.services.certification_versions import runtime
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.outcomes import package_outcomes
from tests.integration import test_certification_enrollments as base
from tests.test_certification_outcome_rubric import candidate, VERSION

repo = base.repo
pytestmark = base.pytestmark


async def enroll(repo, monkeypatch, tmp_path, kind):
    if kind == 'competency':
        fixture = candidate.__wrapped__(tmp_path)
        path = fixture.folder.parent / 'registry.json'
        registry = json.loads(path.read_text())
        registry['releases'][VERSION].update(state='published', supported_for_existing=True)
        registry['new_enrollment_default'] = VERSION
        path.write_text(json.dumps(registry))
        repo.catalog = CourseCatalog(fixture.folder.parent)
    learner = await repo.ensure_initial('chat-assessment-reader')
    package = repo.catalog.load(learner.course_version)
    monkeypatch.setattr(runtime, 'EnrollmentRepository', lambda: repo)
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    return learner, package


@pytest.mark.parametrize('kind', ['legacy', 'competency'])
async def test_all_module_coaching_routes_are_pinned_and_do_not_write_progress(repo, monkeypatch, tmp_path, kind):
    learner, package = await enroll(repo, monkeypatch, tmp_path, kind)
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner.user_id))
    before = [await collection.find({}).to_list(None) for collection in
              (repo.progress, repo.enrollments, repo.selections)]
    contract = package_outcomes(package)
    progress_result = await chat_tools.get_certification_progress(context)
    assert progress_result['maximum_stars'] == package.manifest.maximum_stars
    assert progress_result['credit_basis'] == ('required_outcomes' if kind == 'competency' else 'legacy_rubric')
    if kind == 'legacy':
        assert 'progression_policy' not in progress_result
    else:
        assert progress_result['progression_policy']['required_modules'] == len(package.manifest.modules)
    for module in package.manifest.modules:
        result = await chat_tools.get_certification_module(context, module.id)
        assert 'error' not in result, result
        assert result['enrollment_id'] == learner.uuid
        assert result['manifest_sha256'] == package.manifest_sha256
        assert result['maximum_stars'] == progress_result['maximum_stars']
        assert result['credit_basis'] == progress_result['credit_basis']
        if kind == 'competency':
            exercise = package.json('exercises.json')[module.id]
            assert result['instructions'] == exercise['instructions']
            assert result['agent_guidance'] == exercise.get('chat_instructions', [])
            required = next(m for m in contract.modules if m.module_id == module.id)
            assert result['assessment_mode'] == 'selected_saved_outcomes'
            assert result['required_outcomes'] == [
                {'outcome_id': o.id, 'statement': o.statement, 'method': o.method} for o in required.outcomes]
            assert result['assessment_keys'] == result['assessment_questions'] == []
            assert result['selected_outcome_completion'] is True
        else:
            exercise = package.json('exercises.json')[module.id]
            assert result['instructions'] == (exercise.get('chat_instructions') or exercise.get('instructions', []))
            assert result['agent_guidance'] == []
            reflective = module.id in ('ai_literacy', 'process_mapping', 'workflow_design')
            assert result['assessment_mode'] == ('legacy_reflection' if reflective else 'legacy_practical')
            assert bool(result['assessment_keys']) is reflective
            assert bool(result['assessment_questions']) is reflective
            assert result['required_outcomes'] == []
            assert result['selected_outcome_completion'] is False
    assert before == [await collection.find({}).to_list(None) for collection in
                      (repo.progress, repo.enrollments, repo.selections)]


@pytest.mark.parametrize('kind', ['legacy', 'competency'])
@pytest.mark.parametrize('route', ['service', 'tool', 'http'])
async def test_obsolete_reflections_cannot_write_a_competency_course(repo, monkeypatch, tmp_path, kind, route):
    learner, _ = await enroll(repo, monkeypatch, tmp_path, kind)
    context = SimpleNamespace(deps=SimpleNamespace(user_id=learner.user_id))
    app = FastAPI()
    app.include_router(certification.router, prefix='/certification')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=learner.user_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for module_id, keys in certification_service.ASSESSMENT_KEYS.items():
            answers = {key: 'Supplied by the synthetic learner.' for key in keys}
            before = (await repo.read_progress(learner.user_id, learner.uuid)).model_dump()
            if route == 'service':
                if kind == 'competency':
                    with pytest.raises(EnrollmentConflict, match='Open module assessment'):
                        await certification_service.store_assessment(learner.user_id, module_id, answers, enrollment_id=learner.uuid)
                else:
                    result = await certification_service.store_assessment(learner.user_id, module_id, answers, enrollment_id=learner.uuid)
                    assert result['stored'] is True
            elif route == 'tool':
                result = await chat_tools.submit_certification_assessment(context, module_id, answers, enrollment_id=learner.uuid)
                if kind == 'competency':
                    assert 'Open module assessment' in result['error']
                    assert 'stored' not in result
                else:
                    assert result['stored'] is True
            else:
                response = await client.post(f'/certification/modules/{module_id}/assessment',
                    params={'enrollment_id': learner.uuid}, json={'answers': answers})
                if kind == 'competency':
                    assert response.status_code == 409
                    assert 'Open module assessment' in response.json()['detail']
                else:
                    assert response.status_code == 200 and response.json()['stored'] is True
            after = (await repo.read_progress(learner.user_id, learner.uuid)).model_dump()
            if kind == 'competency':
                assert after == before
            else:
                assert all(after['modules'][module_id]['self_assessment'][key] == value for key, value in answers.items())
            assert after['total_xp'] == before['total_xp'] == 0
            assert all(not module.get('completed') for module in after['modules'].values())
