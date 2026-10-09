#!/usr/bin/env python3
"""Index retained certification QA evidence without changing acceptance or grades.

Only local files are read. Capture counts include repeated/diagnostic states and
are never treated as test passes, distinct defects, or proof of a live course.
"""
import argparse
from collections import Counter
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE_RUNS = ('certification-2026-10-02-run2', 'certification-2026-10-02-interactions',
                 'certification-2026-10-02-completion')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(root, path):
    return str(path.resolve().relative_to(root.resolve()))


def reference(root, name):
    """Index a repository artifact only; never follow a report outside it."""
    if not isinstance(name, str):
        return None
    path = root / name
    try:
        local = relative(root, path)
    except ValueError:
        return {'path': name, 'available': False, 'reason': 'outside_repository'}
    result = {'path': local, 'available': path.exists()}
    if path.is_file():
        result.update(bytes=path.stat().st_size, sha256=digest(path))
    return result


def capture_row(root, directory, row, *, hash_assets=False):
    identity = row['id']
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', identity):
        raise ValueError('Unsafe capture identity')
    files = {}
    for kind, suffix in [('image', '.png'), ('accessible_snapshot', '.txt'), ('axe', '.axe.json')]:
        path = directory / (identity + suffix)
        local = relative(root, path)
        files[kind] = {'path': local, 'available': path.is_file()}
        if path.is_file():
            files[kind]['bytes'] = path.stat().st_size
            if hash_assets:
                files[kind]['sha256'] = digest(path)
    violations = None
    if files['axe']['available']:
        values = json.loads((directory / (identity + '.axe.json')).read_text())
        violations = [{'id': value['id'], 'node_count': len(value.get('nodes', []))} for value in values]
    return {key: row.get(key) for key in ('id', 'note', 'viewport', 'devicePixelRatio', 'visualViewportScale', 'pageWidth')} | {
        'diagnostic_capture': identity == 'blocked', 'assets': files, 'axe_observations': violations,
    }


def run_row(root, path, checkpoint_ids=()):
    data = json.loads(path.read_text())
    if not isinstance(data.get('captures'), list):
        return None
    baseline = path.parent.name in BASELINE_RUNS
    captures = [capture_row(root, path.parent, row, hash_assets=baseline) for row in data['captures']]
    return {
        'manifest': reference(root, relative(root, path)), 'checkpoints': sorted(checkpoint_ids),
        'baseline_run': baseline, 'captured_at': data.get('capturedAt'), 'reported_commit': data.get('commit'),
        'reported_source_fingerprint': data.get('sourceFingerprint'), 'reported_fixture_fingerprint': data.get('fixtureFingerprint'),
        'reported_build_mode': data.get('buildMode'), 'browser': data.get('browserEngine', 'not_recorded'),
        'browser_version': data.get('browserVersion'), 'native_profile_zoom': data.get('nativeProfileZoom', 1),
        'reported_zoom_equivalent': data.get('zoomEquivalent', 1), 'reported_text_scale': data.get('textScale', 1),
        'reported_scope': data.get('mode'), 'verified_build_manifest': reference(root, data.get('verified_build_manifest')),
        'verified_bundle': reference(root, data.get('verified_bundle')),
        'recorded_errors': data.get('errors'), 'recorded_unmatched_routes': data.get('unmatched'),
        'recorded_observations': data.get('observations'), 'captures': captures,
    }


def build(root):
    checklist = root / 'docs/certification-v5-upgrade-checklist.md'
    progress = root / 'docs/certification-v5-implementation-progress.md'
    report = root / 'docs/reviews/certification-v5-audit.html'
    items = [{'id': match[2], 'accepted': match[1] == 'x', 'requirement': match[3].strip()}
             for match in re.finditer(r'^- \[([ x])\] \*\*(C8-[A-Z0-9]+-\d+) · (.+)$', checklist.read_text(), re.M)]
    text = progress.read_text()
    checkpoints = []
    by_directory = {}
    for match in re.finditer(r'^### Checkpoint (\d+) (.+)\n([\s\S]*?)(?=^### Checkpoint |\Z)', text, re.M):
        number = int(match[1])
        dirs = sorted(set(re.findall(r'artifacts/visual-review/(certification[^/{}\s)`<>]+)', match[3])))
        checkpoints.append({'number': number, 'title': match[2], 'evidence_directories': dirs})
        for name in dirs:
            by_directory.setdefault(name, set()).add(number)
    for name in BASELINE_RUNS:
        by_directory.setdefault(name, set())
    runs, sources, missing, invalid, packages = [], [], [], [], []
    for name, ids in sorted(by_directory.items()):
        directory = root / 'artifacts/visual-review' / name
        if not directory.is_dir():
            missing.append(relative(root, directory))
            continue
        # Browser manifests are at the root or in named run subdirectories.
        # rglob covers older nested reruns while only decoding manifest.json.
        for path in sorted(directory.rglob('manifest.json')):
            try:
                row = run_row(root, path, ids)
                if row:
                    runs.append(row)
                else:
                    data = json.loads(path.read_text())
                    if data.get('release_id') and data.get('rubric_id'):
                        packages.append({'manifest': reference(root, relative(root, path)),
                                         'release_id': data['release_id'], 'rubric_id': data['rubric_id'],
                                         'checkpoints': sorted(ids), 'scope': 'isolated retained QA package; not a published course'})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                invalid.append({'path': relative(root, path), 'error': str(exc)})
        for pattern in ('source-hashes*.json', 'isolated-source*.json', 'checkpoint.json'):
            for path in sorted(directory.glob(pattern)):
                sources.append(reference(root, relative(root, path)))
    for run in runs:
        for capture in run['captures']:
            missing.extend(asset['path'] for asset in capture['assets'].values() if not asset['available'])
    baseline_captures = [capture for run in runs if run['baseline_run'] for capture in run['captures'] if not capture['diagnostic_capture']]
    views = Counter(f"{c['viewport']['width']}x{c['viewport']['height']}" for run in runs for c in run['captures'] if c.get('viewport'))
    catalog = root / 'backend/certification-data/courses'
    for path in sorted(catalog.glob('*/manifest.json')):
        data = json.loads(path.read_text())
        packages.append({'manifest': reference(root, relative(root, path)), 'release_id': data.get('release_id'),
                         'rubric_id': data.get('rubric_id'), 'scope': 'retained local package; not a publication assertion'})
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    return {
        'schema_version': 1, 'scope': 'Local evidence inventory; not a QA acceptance decision or reassessment',
        'working_head_at_inventory': head,
        'checklist': reference(root, relative(root, checklist)), 'progress_log': reference(root, relative(root, progress)),
        'counts': {'accepted': sum(item['accepted'] for item in items), 'open': sum(not item['accepted'] for item in items),
                   'items': len(items), 'checkpoints': len(checkpoints), 'browser_runs': len(runs),
                   'recorded_captures_including_diagnostics_and_repeats': sum(len(run['captures']) for run in runs),
                   'baseline_selected_captures': len(baseline_captures)},
        'baseline': {'report': reference(root, relative(root, report)), 'selected_runs': list(BASELINE_RUNS),
                     'expected_selected_captures': 151, 'excludes_capture_id': 'blocked',
                     'contract_probe': reference(root, 'artifacts/visual-review/certification-2026-10-02-run2/contracts.json'),
                     'grades': 'Original six dimension and eleven module grades remain in the unchanged linked report.'},
        'course_registry': reference(root, 'backend/certification-data/courses/registry.json'),
        'retained_packages': packages, 'items': items, 'checkpoints': checkpoints, 'source_records': sources,
        'browser_runs': runs, 'recorded_viewports': dict(sorted(views.items())),
        'missing_artifacts': sorted(set(missing)), 'invalid_manifests': invalid,
        'limits': [
            'Repeated states, old builds and failed diagnostics are retained. Counts do not establish acceptance or a quality score.',
            'Reported source fingerprints may describe the shared working tree. Prefer an explicit frozen build manifest and archived bundle when recorded.',
            'A commit plus dirty-tree fingerprint is not a complete source archive. Missing build provenance is not reconstructed or claimed.',
            'Original selected baseline assets are SHA256-hashed. Later capture files are inventoried for presence and size; their manifests are hashed.',
            'Browser fixtures do not prove durable persistence, real grading, lab execution, assistive technology or learner comprehension.',
            'Live-model calibration remains deferred. Actual cohort reconciliation, rollout, live labs, assistive technology and learner observation remain open.',
        ],
    }


def render(ledger, *, prefix='../..', json_name='certification-v5-evidence-ledger.json'):
    def link(path, label):
        return f'<a href="{escape(prefix + "/" + path, quote=True)}">{escape(label)}</a>'
    counts = ledger['counts']
    rows = []
    for run in ledger['browser_runs']:
        path = run['manifest']['path']
        widths = ', '.join(sorted({str(c['viewport']['width']) for c in run['captures'] if c.get('viewport')}))
        context = 'Baseline' if run['baseline_run'] else 'Checkpoints ' + ', '.join(map(str, run['checkpoints']))
        provenance = 'Frozen build linked' if run['verified_build_manifest'] else 'Reported fingerprint only'
        rows.append(f'<tr><td>{link(path, path.removeprefix("artifacts/visual-review/"))}<small>{escape(context)}</small></td>'
                    f'<td>{len(run["captures"])}</td><td>{escape(widths)}</td><td>{escape(str(run["browser"]))}<br>Native zoom {run["native_profile_zoom"]}×; text {run["reported_text_scale"]}×</td>'
                    f'<td>{escape(provenance)}<small>{escape(str(run["reported_scope"]))}</small></td></tr>')
    missing = ''.join(f'<li>{escape(path)}</li>' for path in ledger['missing_artifacts']) or '<li>No missing referenced capture files or evidence directories found.</li>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Certification QA evidence ledger</title><style>body{{font:16px/1.6 system-ui,sans-serif;color:#172033;background:#fff;margin:0 auto;padding:24px;max-width:1200px}}a{{color:#234eb0}}h1{{line-height:1.2}}small{{display:block;color:#475569}}input{{font:inherit;padding:10px;width:min(90%,650px);border:1px solid #64748b;border-radius:6px}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #cbd5e1}}td:first-child{{overflow-wrap:anywhere;min-width:210px}}:focus-visible{{outline:3px solid #1d4ed8;outline-offset:3px}}.note{{padding:16px;background:#f1f5f9;border:1px solid #cbd5e1}}li{{overflow-wrap:anywhere}}</style>
<main><h1>Certification QA evidence ledger</h1><p><strong>{counts['accepted']} of {counts['items']} checklist items accepted; {counts['open']} open.</strong> This inventory does not raise the audit grades or claim release readiness.</p>
<p>{link('docs/certification-v5-implementation-progress.md','Implementation decisions and limits')} · {link('docs/certification-v5-upgrade-checklist.md','Acceptance checklist')} · {link('docs/reviews/certification-v5-audit.html','Unchanged baseline audit')} · <a href="{escape(json_name, quote=True)}">Full JSON ledger</a></p>
<p class="note">The original {counts['baseline_selected_captures']} selected captures are separate from {counts['recorded_captures_including_diagnostics_and_repeats']} recorded states across {counts['browser_runs']} retained runs. Later counts include repeated states and failure diagnostics. Use the checkpoint log for acceptance; a quiet browser fixture is not proof of live grading.</p>
<h2>Evidence limits</h2><ul>{''.join('<li>'+escape(item)+'</li>' for item in ledger['limits'])}</ul>
<h2>Retained browser runs</h2><label for="filter">Filter by checkpoint, state family, browser or evidence directory</label><p><input id="filter" type="search"></p><p id="count" role="status"></p>
<div class="table" role="region" aria-label="Browser evidence table" tabindex="0"><table><thead><tr><th scope="col">Evidence and checkpoint</th><th scope="col">States</th><th scope="col">CSS widths</th><th scope="col">Browser and enlargement</th><th scope="col">Build and execution scope</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Missing evidence files</h2><ul>{missing}</ul></main><script>const rows=[...document.querySelectorAll('tbody tr')],input=document.querySelector('#filter'),status=document.querySelector('#count');function filter(){{const term=input.value.trim().toLowerCase();for(const row of rows)row.hidden=!row.textContent.toLowerCase().includes(term);status.textContent=rows.filter(row=>!row.hidden).length+' of '+rows.length+' retained runs shown';}}input.addEventListener('input',filter);filter();</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=Path('docs/reviews/certification-v5-evidence-ledger.json'))
    args = parser.parse_args()
    ledger = build(args.root)
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + '\n')
    output.with_suffix('.html').write_text(render(ledger, prefix=os.path.relpath(args.root, output.parent), json_name=output.name))
    print(json.dumps({'counts': ledger['counts'], 'missing_artifacts': len(ledger['missing_artifacts']),
                      'invalid_manifests': len(ledger['invalid_manifests']), 'output': str(output)}, indent=2))
    if ledger['counts']['baseline_selected_captures'] != 151 or ledger['missing_artifacts'] or ledger['invalid_manifests']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
