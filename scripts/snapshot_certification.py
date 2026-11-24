#!/usr/bin/env python3
"""Preserve committed certification source and verify/extract it without live data."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SCOPE = [
    'backend/certification-data', 'backend/app', 'backend/pyproject.toml', 'backend/uv.lock',
    'backend/tests/conftest.py', 'backend/tests/test_certification_extraction_fields.py',
    'backend/tests/test_certification_governance.py', 'backend/tests/test_certification_output_delivery.py',
    'backend/tests/test_certificate_pdf.py', 'backend/tests/test_chat_cert_tools.py',
    'frontend/src', 'frontend/public', 'frontend/package.json', 'frontend/package-lock.json',
    'frontend/index.html', 'frontend/vite.config.ts', 'frontend/vitest.config.ts',
    'frontend/tsconfig.json', 'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json',
    'frontend/scripts/export-lessons.mjs',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(directory, destination=None):
    manifest = json.loads((directory / 'manifest.json').read_text())
    payload = (directory / 'course.tar.gz').read_bytes()
    if digest(payload) != manifest['archive_sha256']:
        raise ValueError('Archive digest does not match release metadata')
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        files = {}
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts:
                raise ValueError(f'Unsupported archive entry: {member.name}')
            data = archive.extractfile(member).read()
            files[member.name] = digest(data)
        if files != manifest['files']:
            raise ValueError('File contents do not match the release manifest')
        if destination:
            if destination.exists():
                raise ValueError('Extraction destination must not already exist')
            destination.mkdir(parents=True)
            for member in archive.getmembers():
                if member.isfile():
                    target = destination / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
    print(f"Verified {len(files)} files for {manifest['snapshot_id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--create-from', help='Committed revision to preserve; never reads learner records')
    parser.add_argument('--extract', type=Path, help='New empty destination for verified source')
    args = parser.parse_args()
    if args.create_from:
        revision = subprocess.check_output(['git', 'rev-parse', args.create_from], cwd=ROOT, text=True).strip()
        args.directory.mkdir(parents=True, exist_ok=False)
        payload = subprocess.check_output(['git', 'archive', '--format=tar.gz', revision, *SCOPE], cwd=ROOT)
        files = {}
        with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
            for member in archive.getmembers():
                if member.isfile():
                    files[member.name] = digest(archive.extractfile(member).read())
        manifest = {
            'snapshot_id': args.directory.name,
            'source_commit': revision,
            'source_commit_date': subprocess.check_output(['git', 'show', '-s', '--format=%cI', revision], cwd=ROOT, text=True).strip(),
            'status': 'preservation-only',
            'historical_enrollment_version': 'unknown',
            'description': 'Repository course at audit baseline; not evidence of what a past learner saw or earned.',
            'archive_sha256': digest(payload),
            'files': files,
        }
        (args.directory / 'course.tar.gz').write_bytes(payload)
        (args.directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    verify(args.directory, args.extract)


if __name__ == '__main__':
    main()
