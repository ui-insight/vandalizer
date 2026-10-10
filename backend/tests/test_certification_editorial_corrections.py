import json
import os
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.services.certification_versions.catalog import CourseCatalog, CourseCatalogError
from app.services.certification_versions.delivery import CourseDelivery, public_modules
from app.services.certification_versions import editorial_corrections as corrections
from app.services.certification_versions.runtime import CourseOperation, _operation
from app.services.chat_tools import get_certification_lesson

VERSION = 'legacy-2026-10-02.1'


def test_corrections_are_bound_to_real_frozen_lessons_and_share_one_export():
    package = CourseCatalog().load(VERSION, preview=True)
    source = corrections._load()
    original = package.json('lessons.json')
    ids = {lesson['id'] for module in original.values() for lesson in module['lessons']}
    bodies = {lesson['id']: lesson['content'] for module in original.values() for lesson in module['lessons']}
    for notice in source.notices:
        assert notice.manifest_sha256 == package.manifest_sha256
        assert set(notice.lesson_ids) <= ids
        assert notice.assessment_changed is False
        assert set(notice.unversioned_content_sha256) == {hashlib.sha256(bodies[key].encode()).hexdigest() for key in notice.lesson_ids}
    frontend = Path(__file__).resolve().parents[2] / 'frontend/src/components/certification/editorialCorrections.json'
    assert json.loads(frontend.read_text()) == json.loads(corrections.SOURCE.read_text())


def test_wrong_package_unknown_lesson_and_unversioned_content_do_not_inherit_corrections():
    notice = corrections._load().notices[0]
    for manifest, lesson in [('0' * 64, notice.lesson_ids[0]), (notice.manifest_sha256, 'foreign.lesson'), (None, notice.lesson_ids[0])]:
        assert corrections.notices_for(manifest, lesson) == []
    first = corrections.notices_for(notice.manifest_sha256, notice.lesson_ids[0])
    first[0]['paragraphs'].clear()
    assert corrections.notices_for(notice.manifest_sha256, notice.lesson_ids[0])[0]['paragraphs']


@pytest.mark.asyncio
@pytest.mark.parametrize('notice_index', range(len(corrections._load().notices)))
async def test_panel_direct_lesson_and_chat_keep_original_teaching_and_expose_same_correction(notice_index):
    package = CourseCatalog().load(VERSION, preview=True)
    original_bytes = package.artifact_bytes
    lesson_id = corrections._load().notices[notice_index].lesson_ids[0]
    module_id = lesson_id.split('.')[0]
    assert lesson_id.startswith(module_id + '.')
    original = next(row for row in package.json('lessons.json')[module_id]['lessons'] if row['id'] == lesson_id)
    panel = next(row for row in public_modules(package) if row['id'] == module_id)
    rendered = next(row for row in panel['lessons'] if row['id'] == lesson_id)
    delivery = CourseDelivery()
    delivery._resolve = AsyncMock(return_value=(SimpleNamespace(uuid='a' * 32, course_version=VERSION), package, None))
    direct = await delivery.lesson('user1', 'a' * 32, module_id, lesson_id)
    token = _operation.set(CourseOperation('user1', package, SimpleNamespace(enrollment_id='a' * 32), False))
    try:
        chat = await get_certification_lesson(SimpleNamespace(deps=SimpleNamespace(user_id='user1')), module_id, lesson_id=lesson_id, enrollment_id='a' * 32)
    finally:
        _operation.reset(token)
    assert chat.get('error') is None
    assert rendered['editorialNotices'] == direct['editorial_notices'] == chat['editorial_notices']
    assert chat['content'] == direct['content'] == rendered['content'] == original['content']
    assert chat['lesson_revision'] == direct['revision'] == rendered['revision'] == original['revision']
    assert direct.get('knowledge_check') == chat['knowledge_check'] == original.get('knowledge_check')
    assert package.artifact_bytes == original_bytes
    assert set(chat['editorial_notices'][0]) == {'id', 'issued_at', 'title', 'paragraphs', 'assessment_changed', 'identity_basis'}
    unknown = corrections.notices_for(None, None, original['content'])
    assert unknown and unknown[0]['identity_basis'] == 'preserved_lesson_text'
    assert 'course_version' not in unknown[0] and 'manifest_sha256' not in unknown[0]
    assert corrections.notices_for(None, lesson_id, original['content'] + ' changed') == []
    assert corrections.notices_for('f' * 64, lesson_id, original['content']) == []
    if path := os.environ.get('CERTIFICATION_EDITORIAL_EXPORT'):
        Path(path).write_text(json.dumps({'course': {**package.summary(), 'modules': public_modules(package),
            **package.json('course-structure.json')}, 'lesson': chat}, indent=2) + '\n')


@pytest.mark.parametrize('change', ['assessment', 'duplicate', 'empty'])
def test_ambiguous_or_assessment_changing_notices_are_rejected(change):
    data = json.loads(corrections.SOURCE.read_text())
    if change == 'assessment':
        data['notices'][0]['assessment_changed'] = True
    elif change == 'duplicate':
        data['notices'].append(data['notices'][0])
    else:
        data['notices'][0]['paragraphs'] = ['']
    with pytest.raises(ValidationError):
        corrections.EditorialNotices.model_validate(data)


def test_unavailable_corrections_do_not_silently_deliver_uncorrected_guidance(tmp_path, monkeypatch):
    corrections._load.cache_clear()
    monkeypatch.setattr(corrections, 'SOURCE', tmp_path / 'missing.json')
    try:
        with pytest.raises(CourseCatalogError, match='guidance is unavailable'):
            corrections.notices_for('a' * 64, 'module.lesson')
    finally:
        corrections._load.cache_clear()


@pytest.mark.parametrize('module_id', ['governance', 'ai_literacy'])
def test_module_notices_preserve_original_description_and_require_exact_identity(module_id):
    package = CourseCatalog().load(VERSION, preview=True)
    original_bytes = package.artifact_bytes
    original = next(row for row in package.json('panel-modules.json') if row['id'] == module_id)
    rendered = next(row for row in public_modules(package) if row['id'] == module_id)
    notice = next(row for row in corrections._load().module_notices if module_id in row.module_ids)
    assert notice.manifest_sha256 == package.manifest_sha256
    assert notice.unversioned_content_sha256 == [hashlib.sha256(original['description'].encode()).hexdigest()]
    assert rendered['description'] == original['description']
    assert rendered['editorialNotices'] == corrections.module_notices_for(package.manifest_sha256, module_id)
    assert rendered['editorialNotices'][0]['identity_basis'] == 'course_manifest'
    assert set(rendered['editorialNotices'][0]) == {'id', 'issued_at', 'title', 'paragraphs', 'assessment_changed', 'identity_basis'}
    assert corrections.module_notices_for(None, module_id) == []
    assert corrections.module_notices_for('f' * 64, module_id, original['description']) == []
    assert corrections.module_notices_for(package.manifest_sha256, 'foreign') == []
    assert corrections.module_notices_for(None, module_id, original['description'] + ' changed') == []
    matched = corrections.module_notices_for(None, module_id, original['description'])
    assert matched[0]['identity_basis'] == 'preserved_module_description'
    matched[0]['paragraphs'].clear()
    assert corrections.module_notices_for(None, module_id, original['description'])[0]['paragraphs']
    assert package.artifact_bytes == original_bytes


@pytest.mark.parametrize('change', ['assessment', 'duplicate_id', 'duplicate_target', 'empty_target'])
def test_invalid_module_corrections_are_rejected(change):
    data = json.loads(corrections.SOURCE.read_text())
    notice = data['module_notices'][0]
    if change == 'assessment':
        notice['assessment_changed'] = True
    elif change == 'duplicate_id':
        notice['id'] = data['notices'][0]['id']
    elif change == 'duplicate_target':
        notice['module_ids'] *= 2
    else:
        notice['module_ids'] = ['']
    with pytest.raises(ValidationError):
        corrections.EditorialNotices.model_validate(data)


@pytest.mark.asyncio
async def test_historical_star_notice_reaches_exercise_and_tutor_without_rewriting_criteria(monkeypatch):
    from app.services import certification_service
    from app.services.chat_tools import get_certification_module
    package = CourseCatalog().load(VERSION, preview=True)
    original = package.json('exercises.json')['multi_step']
    module = next(row for row in public_modules(package) if row['id'] == 'multi_step')
    token = _operation.set(CourseOperation('user1', package, SimpleNamespace(enrollment_id='a' * 32), False))
    monkeypatch.setattr(certification_service, 'get_progress_dict', AsyncMock(return_value={'modules': {}}))
    try:
        exercise = certification_service.get_exercise('multi_step')
        chat = await get_certification_module(SimpleNamespace(deps=SimpleNamespace(user_id='user1')), 'multi_step')
    finally:
        _operation.reset(token)
    assert chat.get('error') is None
    assert chat['editorial_notices'] == exercise['editorial_notices'] == module['editorialNotices']
    assert chat['star_criteria'] == exercise['star_criteria'] == original['star_criteria']
    assert {key: value for key, value in exercise.items() if key != 'editorial_notices'} == original
    for text in [module['description'], original['overview']]:
        matched = corrections.module_notices_for(None, 'multi_step', text)
        assert matched[0]['identity_basis'] == 'preserved_module_description'
        assert corrections.module_notices_for('f' * 64, 'multi_step', text) == []
    assert package.json('exercises.json')['multi_step'] == original
    if path := os.environ.get('CERTIFICATION_MODULE_EXPORT'):
        Path(path).write_text(json.dumps({'course': {**package.summary(), 'modules': public_modules(package),
            **package.json('course-structure.json')}, 'module': chat, 'exercise': exercise}, indent=2) + '\n')
