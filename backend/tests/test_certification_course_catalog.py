import asyncio
import hashlib
import json
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.grading import grade, load_rubric, pinned_progress

VERSION = 'legacy-2026-10-02.1'


@pytest.fixture
def catalog(tmp_path):
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    return CourseCatalog(tmp_path / 'courses')


def set_state(catalog, state, supported=True):
    path = catalog.root / 'registry.json'
    value = json.loads(path.read_text())
    value['releases'][VERSION].update(state=state, supported_for_existing=supported)
    path.write_text(json.dumps(value))


def test_draft_is_readable_for_preview_but_never_enrollable(catalog):
    assert catalog.load(VERSION, preview=True).summary()['modules_total'] == 11
    with pytest.raises(CourseCatalogError, match='Draft'):
        catalog.load(VERSION, new_enrollment=True)
    with pytest.raises(CourseCatalogError, match='Draft'):
        catalog.load(VERSION)


def test_retiring_new_enrollment_preserves_existing_learners(catalog):
    set_state(catalog, 'published')
    before = catalog.load(VERSION, new_enrollment=True)
    set_state(catalog, 'retired')
    after = catalog.load(VERSION)
    assert after.manifest_bytes == before.manifest_bytes
    assert after.artifact_bytes == before.artifact_bytes
    with pytest.raises(CourseCatalogError, match='closed'):
        catalog.load(VERSION, new_enrollment=True)


@pytest.mark.parametrize('asset', ['manifest.json', 'lessons.json', 'exercises.json', 'rubric.py', 'documents/nih-r01-neuroscience.pdf'])
def test_changed_published_files_are_rejected(catalog, asset):
    set_state(catalog, 'published')
    path = catalog.root / VERSION / asset
    path.write_bytes(path.read_bytes() + b'\nmodified')
    with pytest.raises(CourseCatalogError, match='integrity'):
        catalog.load(VERSION)


def test_returned_content_cannot_mutate_another_reader(catalog):
    package = catalog.load(VERSION, preview=True)
    package.json('lessons.json')['ai_literacy']['lessons'].clear()
    package.manifest.artifacts.clear()
    assert len(package.json('lessons.json')['ai_literacy']['lessons']) == 9
    assert package.manifest.artifacts
    assert package.summary()['maximum_xp'] == 2675


def test_draft_edits_cannot_change_an_already_loaded_package(catalog):
    package = catalog.load(VERSION, preview=True)
    path = catalog.root / VERSION / 'lessons.json'
    path.write_text('{}')
    assert package.json('lessons.json')['ai_literacy']['lessons'][0]['id']
    with pytest.raises(CourseCatalogError):
        catalog.load(VERSION, preview=True)


def test_unknown_version_never_falls_back_to_latest(catalog):
    with pytest.raises(CourseCatalogError, match='Unknown'):
        catalog.load('missing-course')


async def test_preserved_rubric_uses_pinned_progress_for_concurrent_learners(catalog):
    set_state(catalog, 'published')
    package = catalog.load(VERSION)
    passing = SimpleNamespace(user_id='one', course_version=VERSION, modules={'ai_literacy': {'self_assessment': {'experience': 'some', 'comfort': 'some', 'concern': 'some'}}})
    failing = SimpleNamespace(user_id='two', course_version=VERSION, modules={})
    rubric = load_rubric(package)

    async def delayed_read(user_id):
        await asyncio.sleep(0)
        return pinned_progress(user_id)

    with patch.object(rubric, 'get_progress', delayed_read):
        success, failure = await asyncio.gather(grade(package, passing, 'ai_literacy'), grade(package, failing, 'ai_literacy'))
    assert success['passed'] is True
    assert failure['passed'] is False
    assert success['course_version'] == VERSION
    assert success['manifest_sha256'] == package.manifest_sha256
    with pytest.raises(CourseCatalogError, match='pinned'):
        pinned_progress('one')


async def test_grading_rejects_a_different_enrollment_version(catalog):
    set_state(catalog, 'published')
    with pytest.raises(CourseCatalogError, match='versions differ'):
        await grade(catalog.load(VERSION, preview=True), SimpleNamespace(user_id='one', course_version='another'), 'ai_literacy')


async def test_draft_grading_requires_an_explicit_preview(catalog):
    package = catalog.load(VERSION, preview=True)
    progress = SimpleNamespace(user_id='preview', course_version=VERSION, modules={})
    with pytest.raises(CourseCatalogError, match='supported published'):
        await grade(package, progress, 'ai_literacy')
    assert (await grade(package, progress, 'ai_literacy', preview=True))['passed'] is False


@pytest.mark.parametrize('registry', [[], {'schema_version': 1, 'releases': {}, 'new_enrollment_default': 'absent'}])
def test_invalid_registry_fails_with_a_catalog_error(catalog, registry):
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    with pytest.raises(CourseCatalogError):
        catalog.registry()


def test_installed_rubric_must_match_the_release(catalog):
    path = catalog.root / VERSION
    (path / 'rubric.py').write_text('raise RuntimeError("must never execute")')
    manifest = json.loads((path / 'manifest.json').read_text())
    manifest['artifacts']['rubric.py'] = hashlib.sha256((path / 'rubric.py').read_bytes()).hexdigest()
    (path / 'manifest.json').write_text(json.dumps(manifest))
    registry = json.loads((catalog.root / 'registry.json').read_text())
    registry['releases'][VERSION]['manifest_sha256'] = hashlib.sha256((path / 'manifest.json').read_bytes()).hexdigest()
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    with pytest.raises(CourseCatalogError, match='Installed rubric'):
        load_rubric(catalog.load(VERSION, preview=True))


def test_ci_guard_preserves_published_and_retired_definitions():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('cert_release_check', Path(__file__).resolve().parents[2] / 'scripts/check_certification_releases.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    original = {'releases': {'old': {'state': 'published', 'manifest_sha256': 'a' * 64, 'supported_for_existing': True}}}
    retired = {'releases': {'old': {**original['releases']['old'], 'state': 'retired'}}}
    checker.check_published_history(original, retired)
    for replacement in [None, {**retired['releases']['old'], 'manifest_sha256': 'b' * 64}, {**retired['releases']['old'], 'state': 'draft'}, {**retired['releases']['old'], 'supported_for_existing': False}]:
        current = {'releases': {'old': replacement} if replacement else {}}
        with pytest.raises(CourseCatalogError):
            checker.check_published_history(original, current)


def test_legacy_rubric_cannot_award_new_competency_outcomes():
    package = SimpleNamespace(manifest=SimpleNamespace(rubric_id='legacy-2026-10-02', artifacts={'outcomes.json': 'a' * 64}))
    with pytest.raises(CourseCatalogError, match='cannot assess new competency'):
        load_rubric(package)


@pytest.mark.parametrize('offers', [[], None, {'missing': []}, {VERSION: VERSION}, {VERSION: [VERSION]}, {VERSION: ['missing']}, {VERSION: [[]]}])
def test_optional_course_offers_reject_malformed_or_unknown_targets(catalog, offers):
    path = catalog.root / 'registry.json'
    registry = json.loads(path.read_text())
    registry['optional_upgrade_offers'] = offers
    path.write_text(json.dumps(registry))
    with pytest.raises(CourseCatalogError, match='unavailable or invalid'):
        catalog.registry()
