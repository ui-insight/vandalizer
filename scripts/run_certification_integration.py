#!/usr/bin/env python3
"""Run an exhaustive deterministic shard of certification persistence cases.

Every case gets a disposable database from its fixture. The connection must be
explicit; application connection settings are never used as a fallback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'


def select_shard(node_ids, shard_index, shard_count):
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError('Shard index must be within the positive shard count')
    if len(set(node_ids)) != len(node_ids):
        raise ValueError('Collected test identities must be unique')
    return sorted(node for node in node_ids
                  if int(hashlib.sha256(node.encode()).hexdigest(), 16) % shard_count == shard_index)


def collect():
    files = sorted(path.relative_to(BACKEND).as_posix()
                   for path in (BACKEND / 'tests/integration').glob('test_certification_*.py'))
    if not files:
        raise ValueError('No certification integration files were found')
    result = subprocess.run([sys.executable, '-m', 'pytest', *files, '--collect-only', '-q'],
                            cwd=BACKEND, capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stdout + result.stderr)
        raise ValueError('Certification collection failed; no partial shard can run')
    nodes = [line.strip() for line in result.stdout.splitlines()
             if line.startswith('tests/integration/test_certification_') and '::' in line]
    if not nodes or {node.split('::', 1)[0] for node in nodes} != set(files):
        raise ValueError('Every discovered certification file must collect at least one test')
    return files, nodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--shard-count', type=int, default=1)
    parser.add_argument('--collect-only', action='store_true')
    parser.add_argument('--report', type=Path, help='Write exact collected and selected test identities')
    parser.add_argument('--junitxml', type=Path)
    args = parser.parse_args()
    try:
        select_shard([], args.shard_index, args.shard_count)
        if not args.collect_only and not os.environ.get('CERTIFICATION_TEST_MONGO_URL'):
            raise ValueError('Set CERTIFICATION_TEST_MONGO_URL to an explicitly authorized disposable MongoDB')
        files, nodes = collect()
        selected = select_shard(nodes, args.shard_index, args.shard_count)
        if not selected:
            raise ValueError('The requested shard has no tests; reduce the shard count')
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = {'schema_version': 1, 'shard_index': args.shard_index, 'shard_count': args.shard_count,
              'files': files, 'collected_count': len(nodes), 'selected_count': len(selected),
              'collected_sha256': hashlib.sha256('\n'.join(sorted(nodes)).encode()).hexdigest(),
              'selected_node_ids': selected, 'live_model_calibration': False}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Certification shard {args.shard_index + 1}/{args.shard_count}: {len(selected)} of {len(nodes)} cases from {len(files)} files', flush=True)
    if args.collect_only:
        return 0
    command = [sys.executable, '-m', 'pytest', *selected, '-q']
    if args.junitxml:
        command += ['--junitxml', str(args.junitxml.resolve())]
    return subprocess.run(command, cwd=BACKEND).returncode


if __name__ == '__main__':
    sys.exit(main())
