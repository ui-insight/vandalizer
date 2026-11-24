"""QA staging publication is explicit, recorded and unusable in production.

Synthetic readiness metadata lets testers complete a staging course. It never
weakens the production gate: production publication still blocks, and only the
named production-evidence findings are waived for a marked package published to
a separate catalog.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from app.services.certification_versions import authoring, delivery
from app.services.certification_versions.authoring import publish
from app.services.certification_versions.catalog import (CATALOG_ROOT, QA_STAGING_MARKER, CourseCatalog,
                                                         CourseCatalogError)
from app.services.certification_versions.release_impact import inspect_catalogs
from tests import test_certification_outcome_rubric as rubric_fixtures
from tests.test_certification_release_impact import inventory

candidate = rubric_fixtures.candidate
SOURCE_ID = 'legacy-2026-10-02.1'
QA = {'reason': 'Staging QA of the 5.0 course', 'actor': 'qa-operator'}


def environment(monkeypatch, name):
    monkeypatch.setenv('ENVIRONMENT', name)
    monkeypatch.setenv('JWT_SECRET_KEY', 'synthetic-test-secret-' + 'x' * 40)


def mark(candidate):
    (candidate.folder / QA_STAGING_MARKER).write_text(json.dumps({'kind': 'certification_qa_staging_package'}))
    def add(manifest):
        manifest['artifacts'][QA_STAGING_MARKER] = ''
    candidate.package = candidate.reload(add)
    return candidate


@pytest.fixture
def staging(candidate, tmp_path):
    """One staging catalog holding the published continuation source and the target draft."""
    root = candidate.folder.parent
    shutil.copytree(CATALOG_ROOT / SOURCE_ID, root / SOURCE_ID)
    registry = json.loads((root / 'registry.json').read_text())
    registry['releases'][SOURCE_ID] = json.loads((CATALOG_ROOT / 'registry.json').read_text())['releases'][SOURCE_ID]
    (root / 'registry.json').write_text(json.dumps(registry))
    catalog = CourseCatalog(root)
    publish(catalog, SOURCE_ID, expected_digest=catalog.load(SOURCE_ID, preview=True).manifest_sha256)
    return catalog


def review(catalog, candidate, observed=None):
    observed = observed if observed is not None else inventory()
    return inspect_catalogs(catalog, SOURCE_ID, catalog, candidate.package.manifest.release_id, inventory=observed), observed


def attempt(catalog, candidate, report, observed, **kwargs):
    return publish(catalog, candidate.package.manifest.release_id, expected_digest=candidate.package.manifest_sha256,
                   impact_report=report, inventory=observed, **kwargs)


def test_marked_package_publishes_only_as_recorded_qa_staging(staging, candidate, monkeypatch):
    mark(candidate)
    report, observed = review(staging, candidate)
    codes = {item['code'] for item in report['blocking_findings']}
    assert codes == {'runtime_compatibility_evidence_required', 'rollout_evidence_required', 'qa_staging_package'}
    before = (staging.root / 'registry.json').read_bytes()
    with pytest.raises(CourseCatalogError, match='cannot be published for production'):
        attempt(staging, candidate, report, observed)
    assert (staging.root / 'registry.json').read_bytes() == before

    record = attempt(staging, candidate, report, observed, qa_staging=QA)
    entry = staging.registry()['releases'][candidate.package.manifest.release_id]
    assert entry['state'] == 'published'
    assert entry['publication'] == record
    assert record['mode'] == 'qa_staging' and record['production_authorized'] is False
    assert record['impact_report_sha256'] == report['report_sha256']
    assert record['source_release_id'] == SOURCE_ID
    assert sorted(record['waived_findings']) == sorted(codes)
    assert (record['reason'], record['actor']) == (QA['reason'], QA['actor'])
    assert 'new_enrollment_default' not in staging.registry()

    environment(monkeypatch, 'staging')
    package = staging.load(candidate.package.manifest.release_id, new_enrollment=True)
    assert package.summary()['authorization'] == 'qa_staging_not_production'
    environment(monkeypatch, 'production')
    for kwargs in ({'new_enrollment': True}, {}):
        with pytest.raises(CourseCatalogError, match='QA staging only'):
            staging.load(candidate.package.manifest.release_id, **kwargs)


def test_qa_mode_keeps_every_non_production_finding(staging, candidate):
    mark(candidate)
    missing = inspect_catalogs(staging, SOURCE_ID, staging, candidate.package.manifest.release_id)
    with pytest.raises(CourseCatalogError, match='cohort_inventory_missing'):
        publish(staging, candidate.package.manifest.release_id, expected_digest=candidate.package.manifest_sha256,
                impact_report=missing, qa_staging=QA)
    observed = inventory()
    observed['cohorts'].update(active=0, inconsistent=1)
    reconcile, _ = review(staging, candidate, observed)
    with pytest.raises(CourseCatalogError, match='cohort_reconciliation_required'):
        attempt(staging, candidate, reconcile, observed, qa_staging=QA)
    assert staging.load(candidate.package.manifest.release_id, preview=True).entry.state == 'draft'


@pytest.mark.parametrize('qa', [{'reason': '', 'actor': 'qa-operator'}, {'reason': 'Staging QA', 'actor': ' '}])
def test_qa_mode_requires_an_accountable_reason_and_actor(staging, candidate, qa):
    mark(candidate)
    report, observed = review(staging, candidate)
    with pytest.raises(CourseCatalogError, match='reason'):
        attempt(staging, candidate, report, observed, qa_staging=qa)
    assert staging.load(candidate.package.manifest.release_id, preview=True).entry.state == 'draft'


def test_qa_mode_is_refused_for_unmarked_packages_production_and_the_application_catalog(staging, candidate, monkeypatch):
    report, observed = review(staging, candidate)
    with pytest.raises(CourseCatalogError, match='QA staging marker'):
        attempt(staging, candidate, report, observed, qa_staging=QA)
    # The production gate itself is unchanged for the unmarked candidate.
    with pytest.raises(CourseCatalogError, match='runtime_compatibility_evidence_required'):
        attempt(staging, candidate, report, observed)
    mark(candidate)
    report, observed = review(staging, candidate)
    environment(monkeypatch, 'production')
    with pytest.raises(CourseCatalogError, match='production environment'):
        attempt(staging, candidate, report, observed, qa_staging=QA)
    monkeypatch.delenv('ENVIRONMENT')
    monkeypatch.setattr(authoring, 'CATALOG_ROOT', staging.root)
    with pytest.raises(CourseCatalogError, match='separate staging catalog'):
        attempt(staging, candidate, report, observed, qa_staging=QA)
    assert staging.load(candidate.package.manifest.release_id, preview=True).entry.state == 'draft'


def test_hand_edited_registry_cannot_publish_a_marked_package(staging, candidate):
    mark(candidate)
    registry = json.loads((staging.root / 'registry.json').read_text())
    registry['releases'][candidate.package.manifest.release_id].update(state='published', supported_for_existing=True)
    (staging.root / 'registry.json').write_text(json.dumps(registry))
    with pytest.raises(CourseCatalogError, match='integrity'):
        staging.load(candidate.package.manifest.release_id, new_enrollment=True)


def test_impact_blocks_a_course_definition_the_installed_delivery_cannot_render(staging, candidate, monkeypatch):
    def broken(package):
        raise ValueError('Unsupported packaged case for this delivery code')
    monkeypatch.setattr(delivery, 'public_modules', broken)
    report, _ = review(staging, candidate)
    finding = next(item for item in report['blocking_findings'] if item['code'] == 'target_delivery_unavailable')
    assert 'Unsupported packaged case' in finding['action']
    assert report['compatibility']['learner_course_definition']['status'] == 'unavailable'


def test_cli_names_the_exact_manifest_and_changes_for_a_qa_publication(staging, candidate, tmp_path):
    mark(candidate)
    report, observed = review(staging, candidate)
    report_path, inventory_path = tmp_path / 'impact.json', tmp_path / 'inventory.json'
    report_path.write_text(json.dumps(report))
    inventory_path.write_text(json.dumps(observed))
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    inspected = subprocess.run([sys.executable, str(scripts / 'inspect_certification_release_impact.py'),
        '--source-catalog-root', str(staging.root), '--target-catalog-root', str(staging.root),
        '--source-release-id', SOURCE_ID, '--target-release-id', candidate.package.manifest.release_id,
        '--cohort-inventory', str(inventory_path)], capture_output=True, text=True, check=False)
    assert inspected.returncode == 2
    assert json.loads(inspected.stdout)['report_sha256'] == report['report_sha256']
    assert 'BLOCKED qa_staging_package [QA staging may waive]' in inspected.stderr
    assert candidate.package.manifest_sha256 in inspected.stderr
    result = subprocess.run([sys.executable, str(scripts / 'manage_certification_release.py'), '--catalog-root', str(staging.root),
        'publish', candidate.package.manifest.release_id, '--expected-manifest-sha256', candidate.package.manifest_sha256,
        '--impact-report', str(report_path), '--cohort-inventory', str(inventory_path), '--qa-staging',
        '--reason', QA['reason'], '--actor', QA['actor']], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.split('\nLocal release metadata updated.')[0])
    assert output['publication']['mode'] == 'qa_staging'
    assert output['changes']['target_manifest_sha256'] == candidate.package.manifest_sha256
    assert output['changes']['lessons_changed'] == report['lessons']['changed']
    assert output['release']['authorization'] == 'qa_staging_not_production'


def test_default_catalog_follows_the_configured_staging_root(staging, monkeypatch):
    monkeypatch.setenv('CERTIFICATION_CATALOG_ROOT', str(staging.root))
    assert CourseCatalog().root == staging.root.resolve()
    monkeypatch.delenv('CERTIFICATION_CATALOG_ROOT')
    assert CourseCatalog().root == CATALOG_ROOT
