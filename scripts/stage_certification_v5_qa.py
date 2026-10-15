#!/usr/bin/env python3
"""Build and operate a separate QA staging catalog for the 5.0 course.

Never touches the application catalog or any learner record. Steps:

  prepare OUTPUT       assemble 5.0, mark it as a QA package and stage it with
                       the legacy continuation baseline (both drafts)
  publish OUTPUT       publish the baseline, select it for unknown legacy
                       history, write the impact report, publish 5.0 in
                       recorded QA staging mode and make it the new-learner default
  rollback OUTPUT      return new learners to the baseline and retire 5.0;
                       existing 5.0 enrollments keep their pinned course

The QA package carries synthetic release-candidate flags so testers can earn
credit. Those flags are not calibration evidence, which is why the package is
marked and can only be published with --qa-staging outside production.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.services.certification_versions.authoring import choose_default, publish, retire  # noqa: E402
from app.services.certification_versions.catalog import (CATALOG_ROOT, QA_STAGING_MARKER, CourseCatalog,  # noqa: E402
                                                         CourseCatalogError)
from app.services.certification_versions.grading import load_rubric  # noqa: E402
from app.services.certification_versions.release_impact import change_summary, inspect_catalogs  # noqa: E402
from app.services.certification_versions.rubrics import competency_v5  # noqa: E402
from assemble_certification_v5_preview import DATA, assemble  # noqa: E402

LEGACY = 'legacy-2026-10-02.1'
DEFAULT_RELEASE = 'v5.0-qa-staging.1'
TITLE = 'Vandalizer 5.0 certification (QA staging)'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mark_for_qa(folder: Path, release_id: str):
    """Install the competency runner and synthetic readiness flags, recorded in the marker."""
    preview_manifest = digest(folder / 'manifest.json')
    contract = json.loads((folder / 'outcomes.json').read_text())
    contract['state'] = 'release_candidate'
    for module in contract['modules']:
        for outcome in module['outcomes']:
            outcome['assessment_status'] = 'verified'
    write_json(folder / 'outcomes.json', contract)
    policy = json.loads((folder / 'progression-policy.json').read_text())
    policy['state'] = 'release_candidate'
    write_json(folder / 'progression-policy.json', policy)
    (folder / 'rubric.py').write_bytes(Path(competency_v5.__file__).read_bytes())
    write_json(folder / QA_STAGING_MARKER, {
        'kind': 'certification_qa_staging_package', 'release_id': release_id, 'production_authorized': False,
        'assembled_preview_manifest_sha256': preview_manifest,
        'synthetic_changes': ['outcomes.json state=release_candidate and every assessment_status=verified',
                              'progression-policy.json state=release_candidate',
                              'rubric.py replaced with the installed competency_v5 runner'],
        'statement': 'Synthetic readiness metadata for QA testers only. Not calibration, rollout or production authorization.',
    })
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['title'] = TITLE
    manifest['artifacts'] = {str(path.relative_to(folder)): digest(path)
                             for path in sorted(folder.rglob('*')) if path.is_file() and path.name != 'manifest.json'}
    write_json(folder / 'manifest.json', manifest)


def prepare(output, release_id=DEFAULT_RELEASE, *, data_root=DATA, source_root=CATALOG_ROOT):
    output = Path(output).resolve()
    if output == CATALOG_ROOT.resolve() or output.is_relative_to(CATALOG_ROOT.resolve()):
        raise ValueError('The QA staging catalog must stay outside the application course catalog')
    if output.exists():
        raise ValueError('Use a new staging catalog directory; an existing catalog is never overwritten')
    source = CourseCatalog(source_root)
    legacy_entry = source.registry()['releases'][LEGACY]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.certification-qa-', dir=output.parent) as temporary:
        preview = assemble(Path(temporary) / 'preview', release_id, data_root=data_root)
        staging = Path(temporary) / 'catalog'
        staging.mkdir()
        shutil.copytree(preview / release_id, staging / release_id)
        shutil.copytree(source_root / LEGACY, staging / LEGACY)
        mark_for_qa(staging / release_id, release_id)
        write_json(staging / 'registry.json', {'schema_version': 1, 'releases': {
            LEGACY: {'state': 'draft', 'supported_for_existing': False, 'manifest_sha256': legacy_entry['manifest_sha256']},
            release_id: {'state': 'draft', 'supported_for_existing': False, 'manifest_sha256': digest(staging / release_id / 'manifest.json')},
        }})
        catalog = CourseCatalog(staging)
        for version in (LEGACY, release_id):
            load_rubric(catalog.load(version, preview=True))
        staging.rename(output)
    catalog = CourseCatalog(output)
    return {version: catalog.load(version, preview=True).manifest_sha256 for version in (LEGACY, release_id)}


def qa_release(catalog):
    marked = [version for version in catalog.registry()['releases']
              if QA_STAGING_MARKER in catalog.load(version, preview=True).manifest.artifacts]
    if len(marked) != 1:
        raise CourseCatalogError('The staging catalog must hold exactly one marked QA release')
    return marked[0]


def publish_qa(output, *, inventory, reason, actor):
    """Run the reviewed lifecycle in order; every step uses the ordinary gated commands."""
    catalog = CourseCatalog(Path(output).resolve())
    release_id = qa_release(catalog)
    steps = []
    legacy = catalog.load(LEGACY, preview=True)
    if legacy.entry.state == 'draft':
        publish(catalog, LEGACY, expected_digest=legacy.manifest_sha256)
        steps.append(f'published continuation baseline {LEGACY}')
    if catalog.registry().get('legacy_continuation') != LEGACY:
        choose_default(catalog, LEGACY, legacy_continuation=True)
        steps.append(f'{LEGACY} selected for learners with unknown legacy history')
    report_path = catalog.root / 'reviews' / f'impact-{release_id}.json'
    target = catalog.load(release_id, preview=True)
    if target.entry.state == 'draft':
        report = inspect_catalogs(catalog, LEGACY, catalog, release_id, inventory=inventory)
        report_path.parent.mkdir(exist_ok=True)
        write_json(report_path, report)
        steps.append(f'impact report {report["report_sha256"]} saved to {report_path}')
        record = publish(catalog, release_id, expected_digest=target.manifest_sha256, impact_report=report,
                         inventory=inventory, qa_staging={'reason': reason, 'actor': actor})
        steps.append(f'published {release_id} in QA staging mode; waived {", ".join(record["waived_findings"])}')
    else:
        # A restart after publication keeps the report that publication recorded.
        report = json.loads(report_path.read_text())
        if report['report_sha256'] != (target.entry.publication.impact_report_sha256 if target.entry.publication else None):
            raise CourseCatalogError('The saved impact report differs from the one recorded at publication')
    choose_default(catalog, release_id)
    steps.append(f'{release_id} is the new-learner default')
    return {'steps': steps, 'changes': change_summary(report), 'registry': registry_view(catalog)}


def rollback(output):
    """Return new learners to the baseline and close 5.0 to new enrollment; nothing is deleted."""
    catalog = CourseCatalog(Path(output).resolve())
    release_id = qa_release(catalog)
    choose_default(catalog, LEGACY)
    steps = [f'{LEGACY} is the new-learner default']
    if catalog.load(release_id, preview=True).entry.state == 'published':
        retire(catalog, release_id)
        steps.append(f'{release_id} retired: closed to new learners, still served to its enrolled learners')
    return {'steps': steps, 'registry': registry_view(catalog)}


def registry_view(catalog):
    registry = catalog.registry()
    return {'new_enrollment_default': registry.get('new_enrollment_default'),
            'legacy_continuation': registry.get('legacy_continuation'),
            'releases': {version: {'state': entry['state'], 'manifest_sha256': entry['manifest_sha256'],
                                   'mode': (entry.get('publication') or {}).get('mode')}
                         for version, entry in registry['releases'].items()},
            'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = parser.add_subparsers(dest='action', required=True)
    first = actions.add_parser('prepare')
    first.add_argument('output', type=Path)
    first.add_argument('--release-id', default=DEFAULT_RELEASE)
    second = actions.add_parser('publish')
    second.add_argument('output', type=Path)
    second.add_argument('--cohort-inventory', type=Path, required=True,
                        help='inventory_certification_cohorts.py output for the staging database')
    second.add_argument('--reason', required=True)
    second.add_argument('--actor', required=True)
    third = actions.add_parser('rollback')
    third.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        result = {'catalog': str(args.output.resolve()), 'manifests': prepare(args.output, args.release_id)}
    elif args.action == 'publish':
        result = publish_qa(args.output, inventory=json.loads(args.cohort_inventory.read_text()),
                            reason=args.reason, actor=args.actor)
    else:
        result = rollback(args.output)
    print(json.dumps(result, indent=2))
    print('Staging catalog metadata updated. No learner records were changed.', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (CourseCatalogError, ValueError, OSError) as exc:
        print(f'QA staging operation refused: {exc}', file=sys.stderr)
        sys.exit(2)
