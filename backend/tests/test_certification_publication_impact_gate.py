"""Synthetic readiness flags and edited reports cannot publish a new course."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.services.certification_versions.authoring import publish
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.release_impact import digest, inspect_catalogs
from tests import test_certification_outcome_rubric as rubric_fixtures
from tests.test_certification_release_impact import inventory

candidate = rubric_fixtures.candidate
SOURCE_ID = 'legacy-2026-10-02.1'


@pytest.fixture
def review(candidate, tmp_path):
    source_root = tmp_path / 'source'
    shutil.copytree(CATALOG_ROOT, source_root)
    source = CourseCatalog(source_root)
    publish(source, SOURCE_ID, expected_digest=source.load(SOURCE_ID, preview=True).manifest_sha256)
    target = CourseCatalog(candidate.folder.parent)
    observed = inventory()
    report = inspect_catalogs(source, SOURCE_ID, target, candidate.package.manifest.release_id, inventory=observed)
    return source, target, observed, report


def attempt(candidate, review, report):
    source, target, observed, _ = review
    before = (target.root / 'registry.json').read_bytes()
    try:
        publish(target, candidate.package.manifest.release_id, expected_digest=candidate.package.manifest_sha256,
                impact_report=report, source_catalog=source, inventory=observed)
    finally:
        assert (target.root / 'registry.json').read_bytes() == before
        assert target.load(candidate.package.manifest.release_id, preview=True).entry.state == 'draft'
        assert target.registry().get('new_enrollment_default') is None


def test_ready_flags_without_review_cannot_publish(candidate, review):
    with pytest.raises(CourseCatalogError, match='requires the reviewed publication impact report'):
        attempt(candidate, review, None)


def test_exact_review_reports_remaining_gates_without_publication(candidate, review):
    report = review[3]
    assert {item['code'] for item in report['blocking_findings']} == {
        'runtime_compatibility_evidence_required', 'rollout_evidence_required'}
    with pytest.raises(CourseCatalogError, match='Publication blocked by impact review: runtime_compatibility'):
        attempt(candidate, review, report)


@pytest.mark.parametrize('change', ['missing_digest', 'edited_findings', 'rehash_cleared_gates', 'wrong_target', 'old_source_digest'])
def test_tampered_or_rehashed_report_cannot_clear_release_checks(candidate, review, change):
    report = deepcopy(review[3])
    if change == 'missing_digest':
        del report['report_sha256']
    elif change in ('edited_findings', 'rehash_cleared_gates'):
        report['blocking_findings'] = []
        report['publication_ready'] = True
    elif change == 'wrong_target':
        report['target']['course_version'] = 'another-course'
    else:
        report['source']['manifest_sha256'] = 'a' * 64
    if change not in ('missing_digest', 'edited_findings'):
        report['report_sha256'] = digest({key: value for key, value in report.items() if key != 'report_sha256'})
    with pytest.raises(CourseCatalogError, match='integrity|identity|impact changed'):
        attempt(candidate, review, report)


@pytest.mark.parametrize('change', ['source_registry', 'target_registry', 'inventory', 'target_package'])
def test_stale_review_requires_fresh_comparison(candidate, review, change):
    source, target, observed, report = review
    if change.endswith('_registry'):
        path = (source if change == 'source_registry' else target).root / 'registry.json'
        path.write_bytes(path.read_bytes() + b'\n')
    elif change == 'inventory':
        observed['metadata_sha256'] = 'b' * 64
    else:
        candidate.package = candidate.reload(lambda manifest: manifest.update(description='Changed after review'))
    with pytest.raises(CourseCatalogError, match='impact changed'):
        attempt(candidate, review, report)


def test_cli_refuses_review_gaps_and_preserves_local_registry(candidate, review, tmp_path):
    source, target, observed, report = review
    report_path, inventory_path = tmp_path / 'impact.json', tmp_path / 'inventory.json'
    report_path.write_text(json.dumps(report))
    inventory_path.write_text(json.dumps(observed))
    before = (target.root / 'registry.json').read_bytes()
    command = Path(__file__).resolve().parents[2] / 'scripts/manage_certification_release.py'
    result = subprocess.run([sys.executable, str(command), '--catalog-root', str(target.root), 'publish',
        candidate.package.manifest.release_id, '--expected-manifest-sha256', candidate.package.manifest_sha256,
        '--impact-report', str(report_path), '--source-catalog-root', str(source.root),
        '--cohort-inventory', str(inventory_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert 'runtime_compatibility_evidence_required' in result.stderr
    assert 'rollout_evidence_required' in result.stderr
    assert 'Traceback' not in result.stderr
    assert 'updated' not in result.stdout
    assert (target.root / 'registry.json').read_bytes() == before
