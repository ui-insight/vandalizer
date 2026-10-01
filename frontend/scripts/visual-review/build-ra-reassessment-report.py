"""Package the reassessment with embedded screenshots and portable evidence summaries.

Run from the repository root after browser checks finish. Uses only recorded
local evidence; does not infer test success or alter the baseline report.
"""
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import re
import subprocess
from PIL import Image

root = Path(__file__).resolve().parents[3]
reports = root/'docs/reviews'
artifacts = root/'artifacts/visual-review'
data_path = reports/'2026-10-01-ra-ui-ux.json'
data = json.loads(data_path.read_text())
checklist = (root/'docs/ra-ui-ux-upgrade-checklist.md').read_text()
data['completedItems'] = len(re.findall(r'^- \[x\] \*\*R8-', checklist, re.M))
data['openItems'] = re.findall(r'^- \[ \] \*\*(R8-[^*]+)\*\* (.+)$', checklist, re.M)
data['currentCommit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', 'frontend/src', 'backend/app', 'backend/certification-data'], cwd=root).decode().split('\0')
digest = hashlib.sha256()
for name in sorted(filter(None, files)):
    digest.update(name.encode()+b'\0')
    digest.update((root/name).read_bytes() if (root/name).is_file() else b'[deleted]')
data['implementationSha256'] = digest.hexdigest()

evidence = {'browserSuites': [], 'actualBackend': []}
for manifest in sorted(artifacts.glob('*ra8*/manifest.json')):
    original = json.loads(manifest.read_text())
    captures = original.get('captures', [])
    findings = []
    for capture in captures:
        axe = manifest.parent/(capture['id']+'.axe.json')
        if axe.is_file() and json.loads(axe.read_text()):
            findings.append({'capture': capture['id'], 'violations': json.loads(axe.read_text())})
    evidence['browserSuites'].append({
        'suite': manifest.parent.name,
        **{key: original.get(key) for key in ['mode', 'capturedAt', 'sourceFingerprint', 'fixtureFingerprint', 'browserVersion', 'buildMode']},
        'captureCount': len(captures), 'errors': original.get('errors', []),
        'unmatched': original.get('unmatched', []), 'recordedFindings': findings,
        'captures': [{key: c.get(key) for key in ['id', 'viewport', 'browserZoom', 'textScale', 'pageWidth']} for c in captures],
        'note': 'Historical attempts are retained in this index. Use the selected final evidence, not a total or this index alone, to infer completion.',
    })
for path in sorted(artifacts.glob('*ra8-isolated*/*.json')):
    if path.name == 'manifest.json' or path.name.endswith('.axe.json'):
        continue
    original = json.loads(path.read_text())
    if 'passed_checks' in original:
        evidence['actualBackend'].append({'suite': path.parent.name, 'part': path.name,
            **{key: original[key] for key in ['mode', 'completed', 'passed_checks', 'count'] if key in original}})
data['evidenceIndex'] = '2026-10-01-ra-ui-ux-evidence.json'
selected = list(dict.fromkeys(path for row in data['surfaces'] for path in row['evidence']))
data['selectedScreenshots'] = len(selected)
evidence['selectedScreenshots'] = []
image_data = {}
for name in selected:
    path = artifacts/name
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as source:
        img = source.convert('RGB')
        buf = io.BytesIO(); img.save(buf, format='WEBP', quality=86, method=6)
        image_data[name] = (img.width, img.height, base64.b64encode(buf.getvalue()).decode())
    evidence['selectedScreenshots'].append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})

esc = lambda value: html.escape(str(value), quote=True)
parts = ['''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vandalizer RA usability reassessment — October 1, 2026</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#182536;font:16px/1.6 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px 24px 64px}header,article,section{background:white;border:1px solid #cbd4de;border-radius:8px;padding:24px;margin:20px 0}h1{font-size:clamp(28px,4vw,40px);line-height:1.2}h2{font-size:24px;line-height:1.3}h3{font-size:19px}a{color:#174fa5}a:focus-visible,summary:focus-visible{outline:3px solid #866300;outline-offset:4px}nav{display:flex;flex-wrap:wrap;gap:12px 24px}.notice{border-left:5px solid #916700;background:#fff8df;padding:16px}.small{font-size:13px;color:#46566a}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #ccd4df}th{background:#edf1f6}td:first-child{min-width:180px}.scores{font-weight:650}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:12px 0}img{display:block;max-width:100%;height:auto;max-height:1100px;object-fit:contain;object-position:top;border:1px solid #c7d0da}figcaption{font-size:12px;overflow-wrap:anywhere;color:#46566a}summary{cursor:pointer;font-weight:650;padding:8px 0}li{margin:8px 0}code{overflow-wrap:anywhere}article:target{outline:3px solid #916700}@media(max-width:650px){main{padding:12px}header,article,section{padding:16px}.pair{grid-template-columns:1fr}th,td{padding:7px}}@media print{details{display:block}article{break-inside:avoid}nav{display:none}}
</style></head><body><main>''']
parts.append(f'<header><p class="small">October 1, 2026 · local working tree</p><h1>Vandalizer RA usability reassessment</h1><p class="notice"><strong>{esc(data["status"])}</strong><br>{data["completedItems"]}/108 checklist items complete. Model execution, screen-reader use and representative-user observations are separate open gates.</p><p>{esc(data["method"])}</p><p><strong>Navigation preserved:</strong> Files toggles the file panel; documents and Library tools remain composable.</p><nav aria-label="Report sections"><a href="#scores">Scores</a><a href="#verification">Verification</a><a href="#remaining">Open work</a><a href="#surfaces">Surface evidence</a><a href="#limits">Limits</a></nav></header>')
parts.append('<section id="scores"><h2>Separate desktop and mobile grades</h2><p>Each cell is UI / UX / RA task fit. These are heuristic judgments under the original rubric. No average conceals a weak surface. The September 30 baseline is unchanged.</p><div class="table" role="region" aria-label="Surface score comparison" tabindex="0"><table><thead><tr><th>Area</th><th>Baseline</th><th>Desktop</th><th>Mobile</th></tr></thead><tbody>')
def scores(row): return ' / '.join(f'{row[k]:g}' for k in ['ui', 'ux', 'ra'])
for i, row in enumerate(data['surfaces']):
    parts.append(f'<tr><td><a href="#surface-{i}">{esc(row["surface"])}</a></td><td>{scores(row["baseline"])}</td><td>{scores(row["desktop"])}</td><td>{scores(row["mobile"])}</td></tr>')
parts.append('</tbody></table></div><h3>Original rubric</h3>')
for key, value in data['rubric'].items(): parts.append(f'<p><strong>{esc(key.upper())}:</strong> {esc(value)}</p>')
parts.append('</section><section id="verification"><h2>Verification and implementation</h2>')
for key, value in data['verification'].items(): parts.append(f'<p><strong>{esc(key)}:</strong> {esc(value)}</p>')
parts.append('<p>Detailed item references and dated results are in <a href="../ra-ui-ux-implementation-progress.md">the implementation log</a>, <a href="../ra-ui-ux-upgrade-checklist.md">108-item checklist</a> and <a href="../ra-ui-ux-route-inventory.md">route inventory</a>. The <a href="2026-10-01-ra-ui-ux-evidence.json">portable evidence index</a> distinguishes historical attempts, selected visual evidence and actual local backend checks.</p><p class="small">Source fingerprint: <code>'+esc(data['implementationSha256'])+'</code><br>'+esc(data['deployment'])+'</p></section>')
parts.append('<section id="remaining"><h2>Open work</h2><ul>')
for title, detail in data['openItems']: parts.append(f'<li><strong>{esc(title)}</strong> {esc(detail)}</li>')
parts.append('</ul></section><h2 id="surfaces">Evidence and remaining friction by surface</h2>')
for i, row in enumerate(data['surfaces']):
    parts.append(f'<article id="surface-{i}"><h3>{esc(row["surface"])}</h3><p class="scores">Desktop {scores(row["desktop"])} · Mobile {scores(row["mobile"])}</p><p><strong>Reason for the reassessment:</strong> {esc(row["scoreReason"])}</p><p><strong>Remaining friction / limit:</strong> {esc(row["remainingFriction"])}</p><details><summary>Inspect desktop and mobile evidence</summary><div class="pair">')
    for name in row['evidence']:
        width, height, encoded = image_data[name]
        parts.append(f'<figure><img loading="lazy" width="{width}" height="{height}" alt="{esc(row["surface"])} at {width} pixels wide" src="data:image/webp;base64,{encoded}"><figcaption>{esc(name)} · {width} × {height}</figcaption></figure>')
    parts.append('</div></details></article>')
parts.append('<section id="limits"><h2>Limits and deployment state</h2><ul>'+''.join('<li>'+esc(value)+'</li>' for value in data['limits'])+'</ul><p>Selected screenshots are embedded in this file and survive raw QA cleanup. Source scripts remain reproducible. No user-study observations or model answers were invented. The report is not a production-release sign-off.</p></section></main></body></html>')
data_path.write_text(json.dumps(data, indent=2)+'\n')
(reports/data['evidenceIndex']).write_text(json.dumps(evidence, indent=2)+'\n')
out = data_path.with_suffix('.html'); out.write_text(''.join(parts))
print(f'{out}: {out.stat().st_size/1024/1024:.2f} MiB, {len(selected)} embedded screenshots')
