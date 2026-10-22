"""Release lifecycle changes cannot rewrite requirements or enroll learners."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from app.services.certification_versions.authoring import choose_default, publish, retire
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError

VERSION = 'legacy-2026-10-02.1'


@pytest.fixture
def catalog(tmp_path):
    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    return CourseCatalog(tmp_path / 'courses')


def test_publication_requires_the_reviewed_digest_and_never_selects_a_default(catalog):
    original = catalog.load(VERSION, preview=True)
    with pytest.raises(CourseCatalogError, match='reviewed draft'):
        publish(catalog, VERSION, expected_digest='stale-review')
    assert catalog.load(VERSION, preview=True).entry.state == 'draft'
    publish(catalog, VERSION, expected_digest=original.manifest_sha256)
    published = catalog.load(VERSION, new_enrollment=True)
    assert published.manifest_bytes == original.manifest_bytes
    assert published.artifact_bytes == original.artifact_bytes
    assert 'new_enrollment_default' not in catalog.registry()
    assert 'legacy_continuation' not in catalog.registry()
    with pytest.raises(CourseCatalogError):
        publish(catalog, VERSION, expected_digest=original.manifest_sha256)


def test_retirement_preserves_existing_course_and_rejects_new_enrollment(catalog):
    original = catalog.load(VERSION, preview=True)
    publish(catalog, VERSION, expected_digest=original.manifest_sha256)
    choose_default(catalog, VERSION, legacy_continuation=True)
    retire(catalog, VERSION)
    assert catalog.load(VERSION).artifact_bytes == original.artifact_bytes
    assert catalog.registry()['legacy_continuation'] == VERSION
    with pytest.raises(CourseCatalogError, match='closed'):
        catalog.load(VERSION, new_enrollment=True)


def test_retirement_cannot_break_the_new_learner_default(catalog):
    publish(catalog, VERSION, expected_digest=catalog.load(VERSION, preview=True).manifest_sha256)
    choose_default(catalog, VERSION)
    with pytest.raises(CourseCatalogError, match='default'):
        retire(catalog, VERSION)
    assert catalog.load(VERSION, new_enrollment=True).entry.state == 'published'
    assert catalog.registry()['transition_policy'] == 'optional'


def test_draft_cannot_be_selected_for_initialization(catalog):
    with pytest.raises(CourseCatalogError, match='Draft'):
        choose_default(catalog, VERSION)


def load_creator():
    spec = importlib.util.spec_from_file_location('certification_release_creator', Path(__file__).resolve().parents[2] / 'scripts/create_certification_release.py')
    creator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(creator)
    return creator


@pytest.fixture
def authoring_data(tmp_path):
    root = tmp_path / 'data'
    root.mkdir()
    for name in ('lessons.json', 'exercises.json', 'panel-modules.json', 'course-structure.json'):
        shutil.copyfile(CATALOG_ROOT.parent / name, root / name)
    shutil.copytree(CATALOG_ROOT.parent / 'documents', root / 'documents')
    return root


def test_draft_creation_is_verified_and_cannot_overwrite_an_existing_release(authoring_data):
    creator = load_creator()
    creator.create('new-draft', 'Draft', 'Test only', 'authored-release', data_root=authoring_data)
    catalog = CourseCatalog(authoring_data / 'courses')
    original = catalog.load('new-draft', preview=True)
    with pytest.raises(ValueError, match='cannot be overwritten'):
        creator.create('new-draft', 'Different', 'Changed', 'authored-release', data_root=authoring_data)
    assert catalog.load('new-draft', preview=True).manifest_bytes == original.manifest_bytes
    assert original.entry.state == 'draft'
    assert original.manifest_sha256 == hashlib.sha256(original.manifest_bytes).hexdigest()


@pytest.mark.parametrize('field', ['id', 'revision', 'title', 'content', 'objective', 'variant', 'diagram', 'knowledgeCheck'])
def test_invalid_draft_creation_leaves_no_registered_or_partial_course(authoring_data, field):
    panel_path = authoring_data / 'panel-modules.json'
    panel = json.loads(panel_path.read_text())
    lesson = panel[0]['lessons'][0]
    if field == 'revision':
        lesson[field] += 1
    elif field == 'knowledgeCheck':
        lesson[field] = {'question': 'Out of sync practice?', 'options': [
            {'text': 'A', 'correct': True, 'explanation': 'Different feedback'},
            {'text': 'B', 'correct': False, 'explanation': 'Different correction'}]}
    else:
        lesson[field] = 'Out of sync with chat'
    panel_path.write_text(json.dumps(panel))
    with pytest.raises(CourseCatalogError):
        load_creator().create('broken-draft', 'Draft', 'Test only', 'authored-release', data_root=authoring_data)
    assert not (authoring_data / 'courses/registry.json').exists()
    assert not (authoring_data / 'courses/broken-draft').exists()
    assert not list((authoring_data / 'courses').glob('.draft-*'))


def test_publication_refuses_unverified_outcome_design(tmp_path):
    import hashlib
    import json
    import shutil
    from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
    from app.services.certification_versions.authoring import publish
    import pytest

    shutil.copytree(CATALOG_ROOT, tmp_path / 'courses')
    catalog = CourseCatalog(tmp_path / 'courses')
    version = 'legacy-2026-10-02.1'
    directory = catalog.root / version
    design = json.loads((CATALOG_ROOT.parent / 'drafts/v5.0/outcomes.json').read_text())
    # Keep the supported runner so the outcome readiness guard itself is tested.
    design['rubric_id'] = 'legacy-2026-10-02'
    (directory / 'outcomes.json').write_text(json.dumps(design))
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest['artifacts']['outcomes.json'] = hashlib.sha256((directory / 'outcomes.json').read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    registry = catalog.registry()
    digest = hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()
    registry['releases'][version]['manifest_sha256'] = digest
    (catalog.root / 'registry.json').write_text(json.dumps(registry))
    before = (catalog.root / 'registry.json').read_bytes()
    with pytest.raises(CourseCatalogError, match='verified outcome assessments'):
        publish(catalog, version, expected_digest=digest)
    assert (catalog.root / 'registry.json').read_bytes() == before
