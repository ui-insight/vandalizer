"""Workers prove they serve one coherent release; support learns why one cannot."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.services.certification_versions import release_coherence
from app.services.certification_versions.catalog import CourseCatalog
from app.services.certification_versions.release_coherence import deployment_identity, diagnose_release
from app.services.certification_versions.rubrics import competency_v5
from tests import test_certification_outcome_rubric as rubric_fixtures

candidate = rubric_fixtures.candidate
VERSION = rubric_fixtures.VERSION


@pytest.fixture
def worker(candidate):
    registry_path = candidate.folder.parent / 'registry.json'
    registry = json.loads(registry_path.read_text())
    registry['releases'][VERSION].update(state='published', supported_for_existing=True)
    registry['new_enrollment_default'] = VERSION
    registry_path.write_text(json.dumps(registry))
    return CourseCatalog(candidate.folder.parent)


def copy_worker(worker, tmp_path, name):
    shutil.copytree(worker.root, tmp_path / name)
    return CourseCatalog(tmp_path / name)


def rebuild_lesson(catalog):
    """A same-named package rebuilt with different metadata: what a stale image would serve."""
    folder = catalog.root / VERSION
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['description'] += ' Rebuilt.'
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return folder


def test_identical_workers_agree_and_any_release_difference_changes_the_fingerprint(worker, tmp_path):
    same = copy_worker(worker, tmp_path, 'same')
    first, second = deployment_identity(worker), deployment_identity(same)
    assert first['fingerprint'] == second['fingerprint']
    assert first['releases'][VERSION]['package'] == 'verified_with_installed_runner'
    assert first['catalog_source'] == 'configured' and first['new_enrollment_default'] == VERSION

    rebuilt = copy_worker(worker, tmp_path, 'rebuilt')
    folder = rebuild_lesson(rebuilt)
    registry = json.loads((rebuilt.root / 'registry.json').read_text())
    registry['releases'][VERSION]['manifest_sha256'] = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
    (rebuilt.root / 'registry.json').write_text(json.dumps(registry))
    changed = deployment_identity(rebuilt)
    assert changed['fingerprint'] != first['fingerprint']
    # The rebuilt worker loads its own bytes, never the digest learners pinned.
    assert rebuilt.load(VERSION).manifest_sha256 != worker.load(VERSION).manifest_sha256


def test_installed_code_is_part_of_the_release(worker, tmp_path, monkeypatch):
    code = tmp_path / 'code'
    code.mkdir()
    (code / 'tool_results.py').write_text('CONTRACT = 1\n')
    monkeypatch.setattr(release_coherence, 'CODE_ROOTS', (code,))
    before = deployment_identity(worker)['fingerprint']
    (code / 'tool_results.py').write_text('CONTRACT = 2\n')
    assert deployment_identity(worker)['fingerprint'] != before


def test_support_diagnosis_names_the_incident_and_preserves_work(worker, tmp_path, monkeypatch):
    assert diagnose_release(worker, VERSION)['status'] == 'available'

    missing = copy_worker(worker, tmp_path, 'missing')
    registry = json.loads((missing.root / 'registry.json').read_text())
    registry['releases'].pop(VERSION)
    registry.pop('new_enrollment_default')
    (missing.root / 'registry.json').write_text(json.dumps(registry))
    assert diagnose_release(missing, VERSION)['status'] == 'unknown_on_this_worker'

    tampered = copy_worker(worker, tmp_path, 'tampered')
    rebuild_lesson(tampered)
    diagnosis = diagnose_release(tampered, VERSION)
    assert diagnosis['status'] == 'integrity_failed'
    assert 'Published manifest changed' in diagnosis['detail']
    assert 'not changed' in diagnosis['learner_work']
    assert deployment_identity(tampered)['releases'][VERSION]['package'] == 'unavailable'

    other = tmp_path / 'other_runner.py'
    other.write_text(Path(competency_v5.__file__).read_text() + '\n# different build\n')
    monkeypatch.setattr(competency_v5, '__file__', str(other))
    runner = diagnose_release(worker, VERSION)
    assert runner['status'] == 'runner_unavailable'
    assert 'differs from the pinned course package' in runner['detail']


def test_operator_check_fails_on_a_mismatched_worker(worker, tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts/check_certification_deployment.py'
    run = lambda *extra: subprocess.run([sys.executable, str(script), '--catalog-root', str(worker.root), *extra],  # noqa: E731
                                        capture_output=True, text=True, check=False)
    first = run()
    assert first.returncode == 0, first.stderr
    fingerprint = json.loads(first.stdout)['fingerprint']
    assert run('--expect', fingerprint).returncode == 0
    mismatch = run('--expect', '0' * 64)
    assert mismatch.returncode == 2 and 'INCOHERENT fingerprint' in mismatch.stderr
    rebuild_lesson(worker)
    broken = run('--expect', fingerprint)
    assert broken.returncode == 2 and f'INCOHERENT {VERSION}' in broken.stderr


def test_versioned_deployment_never_falls_back_to_cached_legacy_content(monkeypatch):
    from app.services import certification_service as service
    from app.services.certification_versions import runtime
    from app.services.certification_versions.catalog import CourseCatalogError
    from app.services.certification_versions.legacy_writes import LegacyOperation, legacy_operation
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: False)
    assert service.get_lessons('ai_literacy')['lessons']
    monkeypatch.setattr(runtime, 'versioning_enabled', lambda: True)
    for read in (lambda: service.get_lessons('ai_literacy'), lambda: service.get_exercise('foundations')):
        with pytest.raises(CourseCatalogError, match='pinned course'):
            read()
    token = legacy_operation.set(LegacyOperation('legacy-learner', False))
    try:
        assert service.get_exercise('foundations') is not None
    finally:
        legacy_operation.reset(token)
