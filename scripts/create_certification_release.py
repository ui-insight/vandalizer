#!/usr/bin/env python3
"""Create a local draft course package. Never changes learner enrollment or publishes."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'backend/certification-data'
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.certification_versions.authoring import authoring_lock, write_registry  # noqa: E402
from app.services.certification_versions.catalog import CourseCatalog  # noqa: E402
from app.services.certification_versions.grading import load_rubric  # noqa: E402


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def create(release_id, title, description, provenance, *, data_root=DATA):
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,95}', release_id):
        raise ValueError('Invalid release identity')
    courses = data_root / 'courses'
    with authoring_lock(courses):
        registry_path = courses / 'registry.json'
        registry = CourseCatalog(courses).registry() if registry_path.exists() else {'schema_version': 1, 'releases': {}}
        destination = courses / release_id
        if destination.exists() or release_id in registry['releases']:
            raise ValueError('Release identity already exists; it cannot be overwritten')
        with tempfile.TemporaryDirectory(prefix='.draft-', dir=courses) as staging:
            staging_root = Path(staging)
            target = staging_root / release_id
            target.mkdir()
            build_package(target, release_id, title, description, provenance, data_root)
            entry = {
                'state': 'draft', 'supported_for_existing': False,
                'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(),
            }
            write_json(staging_root / 'registry.json', {'schema_version': 1, 'releases': {release_id: entry}})
            load_rubric(CourseCatalog(staging_root).load(release_id, preview=True))
            target.rename(destination)
            registry['releases'][release_id] = entry
            # A process crash here can leave an unregistered package, never a
            # partial registered course. Keep that evidence for reconciliation.
            write_registry(courses, registry)
    print(f'Created draft {release_id}; no enrollment or active course was changed.')


def build_package(target, release_id, title, description, provenance, data_root):
    for name in ('lessons.json', 'exercises.json', 'panel-modules.json', 'course-structure.json'):
        shutil.copyfile(data_root / name, target / name)
    shutil.copytree(data_root / 'documents', target / 'documents')
    frozen_rubric = ROOT / 'backend/app/services/certification_versions/rubrics/legacy_20261002.py'
    shutil.copyfile(frozen_rubric, target / 'rubric.py')
    constants = {}
    for node in ast.parse(frozen_rubric.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('MODULE_XP', 'MODULE_ORDER'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    panel = json.loads((target / 'panel-modules.json').read_text())
    if [m['id'] for m in panel] != constants['MODULE_ORDER']:
        raise ValueError('Module order differs between panel and rubric')
    for module in panel:
        if module['xp'] != constants['MODULE_XP'][module['id']]:
            raise ValueError('XP differs between panel and rubric')
    assets = {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(target.rglob('*')) if path.is_file()}
    manifest = {
        'schema_version': 1, 'course_id': 'vandal-workflow-architect',
        'release_id': release_id, 'title': title, 'description': description,
        'historical_provenance': provenance, 'rubric_id': 'legacy-2026-10-02',
        'star_bonus_xp': 25, 'maximum_stars': 3,
        'modules': [{'id': module['id'], 'title': module['title'], 'base_xp': module['xp'],
                     'lesson_ids': [lesson['id'] for lesson in module['lessons']],
                     'prerequisites': []} for module in panel],
        'artifacts': assets,
    }
    write_json(target / 'manifest.json', manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release_id')
    parser.add_argument('--title', required=True)
    parser.add_argument('--description', required=True)
    parser.add_argument('--provenance', choices=['continuation-baseline', 'authored-release'], default='authored-release')
    args = parser.parse_args()
    create(args.release_id, args.title, args.description, args.provenance)
