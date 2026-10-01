"""Build a portable HTML audit with embedded evidence from the recorded JSON review.
Run from the repository root: python3 frontend/scripts/visual-review/build-ra-audit-report.py
Requires Pillow. The resulting report does not depend on the temporary capture folder.
"""
import base64
import html
import io
import json
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[3]
data_path=root/'docs/reviews/2026-09-30-ra-ui-ux.json'
d=json.loads(data_path.read_text())
captures=root/'artifacts/visual-review/2026-09-30-ra-audit'
esc=lambda x:html.escape(str(x),quote=True)
all_rows=d['surfaces']+d['roleOverviews']
proof=list(dict.fromkeys(p for r in all_rows+d['findings'] for p in r['evidence']))
proof_ids={p:'proof-'+str(i+1) for i,p in enumerate(proof)}
def evidence_links(items):
 return ' · '.join(f'<a href="#{proof_ids[p]}">{esc(p.split("/")[-1])}</a>' for p in items)
def surface(r,i):
 return f'''<article id="surface-{i}"><h3>{esc(r['surface'])}</h3><p class="scores">UI {r['ui']:.1f} · UX {r['ux']:.1f} · RA usefulness {r['ra']:.1f}</p><p><b>Works:</b> {esc(r['works'])}</p><p><b>Critique:</b> {esc(r['critique'])}</p><p class="evidence">{evidence_links(r['evidence'])}</p></article>'''
parts=['''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vandalizer — RA UI/UX review · September 30, 2026</title><style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#1e293b;background:#f5f6f8;line-height:1.55}*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:36px 28px 80px}header{border-top:6px solid #eab308;background:#fff;padding:32px;border-radius:5px}h1{font-size:clamp(28px,4vw,42px);line-height:1.12;margin:8px 0 20px;letter-spacing:-.04em}h2{font-size:25px;margin:44px 0 14px}h3{font-size:19px;margin:0 0 10px}p{margin:10px 0}a{color:#175ac1;text-decoration:underline;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #9a6b00;outline-offset:3px}.eyebrow{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#596579}.lead{font-size:20px;max-width:850px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}.metric{background:#f6f7fa;border:1px solid #dce1e8;padding:18px}.metric strong{display:block;font-size:36px;line-height:1.2}.small,.evidence{font-size:13px;color:#536174}.evidence{overflow-wrap:anywhere}nav{display:flex;gap:10px 24px;flex-wrap:wrap;margin-top:24px}article{background:white;border:1px solid #dce1e8;padding:24px;margin:14px 0;border-radius:5px}.scores{font-weight:650;color:#35465d}.priority{display:inline-block;font-size:12px;background:#fff2ce;color:#744c00;padding:3px 8px;border-radius:3px;margin:0 8px 10px 0}.p1{background:#ffe5e5;color:#8d2222}table{border-collapse:collapse;width:100%;background:#fff;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #dce1e8}th{background:#e9edf3}td:not(:first-child),th:not(:first-child){text-align:center}.table-wrap{overflow:auto}.list{padding-left:22px}li{margin:8px 0}code{font-size:12px;overflow-wrap:anywhere}details{margin:12px 0;border:1px solid #ccd4df;background:white;padding:14px}summary{cursor:pointer;font-weight:650}figure{margin:18px 0 4px}figure img{display:block;width:auto;height:auto;max-width:100%;max-height:950px;border:1px solid #c9d0da;margin:0 auto}figcaption{font-size:13px;color:#536174;margin-top:10px}.callout{border-left:4px solid #c78c00;background:#fff9e9;padding:18px}.success{border-left-color:#21834b;background:#eef9f1}.source{display:block;font-size:12px;overflow-wrap:anywhere;color:#536174}.proof:target{outline:3px solid #b8870d}.footer{margin-top:35px;border-top:1px solid #cbd5e1;padding-top:20px}@media(max-width:600px){main{padding:18px 12px 40px}header,article{padding:18px}.metrics{gap:6px}.metric{padding:12px 8px}.metric strong{font-size:27px}.metric span{font-size:12px}.lead{font-size:17px}td,th{padding:8px 5px;font-size:12px}}@media print{body{background:white}main{max-width:none;padding:0}details{break-inside:avoid}article{break-inside:avoid}nav{display:none}}
</style></head><body><main><header><div class="eyebrow">Independent fresh pass · September 30, 2026</div><h1>Vandalizer 5.0<br>UI, UX &amp; usefulness for an RA</h1><p class="lead">The core document workflow is useful and increasingly coherent. The broader app is not yet a consistent 8/10 experience: keyboard access, mobile supporting pages and discoverability need another focused pass.</p><div class="metrics">''']
for key,label in [('ui','Visual UI'),('ux','User experience'),('ra','RA task fit')]:parts.append(f'<div class="metric"><strong>{d["overall"][key]:.1f}<small>/10</small></strong><span>{label}</span></div>')
parts.append(f'''</div><p class="small">{esc(d['aggregateNote'])}</p><nav aria-label="Report sections"><a href="#findings">Priorities</a><a href="#scorecard">Scorecard</a><a href="#surfaces">Surface critiques</a><a href="#proof">Screenshots</a><a href="#method">Method &amp; limits</a></nav></header><h2>What to preserve</h2><div class="callout success">The document → Library → run → retry → return journey passed at 1440, 1024, 768, 390 and 320px. The source document stayed in scope. Keep this split-pane model while improving labels and controls.</div><h2 id="findings">Prioritized findings</h2><p>Three P1 groups deserve attention before another decorative polish pass. P2 items improve comprehension and everyday work; P3 improves consistency.</p>''')
for f in d['findings']:
 parts.append(f'''<article><span class="priority {'p1' if f['priority']=='P1' else ''}">{f['priority']} · {f['id']}</span><span class="small">{esc(f['kind'])}</span><h3>{esc(f['title'])}</h3><p>{esc(f['observed'])}</p><p><b>RA impact:</b> {esc(f['impact'])}</p><p><b>Change:</b> {esc(f['recommendation'])}</p><p><b>Acceptance:</b> {esc(f['acceptance'])}</p><p class="evidence">{evidence_links(f['evidence'])}</p>''')
 for path in f['source']:parts.append(f'<code class="source">{esc(path)}</code>')
 parts.append('</article>')
parts.append('<h2 id="scorecard">Major-surface scorecard</h2><p>These are heuristic grades of the sampled states, not measurements from a user study. Supporting-role scores appear separately below.</p><div class="table-wrap"><table><thead><tr><th scope="col">Surface</th><th scope="col">UI</th><th scope="col">UX</th><th scope="col">RA</th></tr></thead><tbody>')
for i,r in enumerate(d['surfaces']):parts.append(f'<tr><td><a href="#surface-{i}">{esc(r["surface"])}</a></td><td>{r["ui"]:.1f}</td><td>{r["ux"]:.1f}</td><td>{r["ra"]:.1f}</td></tr>')
parts.append('</tbody></table></div><h2 id="surfaces">Critique by surface</h2>')
for i,r in enumerate(d['surfaces']):parts.append(surface(r,i))
parts.append('<h2>Supporting-role overviews</h2><p>These roles support the RA workflow. Grades are provisional for the sampled overview, excluded from the overall average.</p>')
for i,r in enumerate(d['roleOverviews']):parts.append(surface(r,'role-'+str(i)))
parts.append('<h2>Recommended next pass</h2><ol class="list">'+''.join('<li>'+esc(x)+'</li>' for x in d['nextAcceptance'])+'</ol>')
parts.append('<h2 id="method">Method, coverage and limits</h2><p>'+esc(d['method'])+'</p>')
for key,value in d['rubric'].items():parts.append('<p><b>'+esc(key.upper())+':</b> '+esc(value)+'</p>')
parts.append(f'<p>140 captures were recorded, including corrected attempts and repeated states; 129 non-blocked unique capture IDs remain in the evidence index. Automated checks found no violations in the 55-state core suite or the 30-state file-to-Library suite. Broader captures found issues documented above. No uncaught page errors were recorded. Zero axe violations does not establish full accessibility; manual inspection found pointer-only controls.</p><ul class="list">'+''.join('<li>'+esc(x)+'</li>' for x in d['limits'])+'</ul>')
parts.append(f'<p class="small">Branch {esc(d["branch"])} · HEAD {esc(d["commit"])} plus the existing split-icon removal.<br>Frontend source SHA256: <code>{d["sourceSha256"]}</code></p>')
parts.append('<h2 id="proof">Embedded visual evidence</h2><p>Selected captures are embedded in this file so the review survives cleanup of the raw QA directory. Expand an item to inspect it. All records, model outputs and scores are synthetic.</p>')
for p in proof:
 im=Image.open(captures/(p+'.png')).convert('RGB');buf=io.BytesIO();im.save(buf,format='WEBP',quality=88,method=6)
 encoded=base64.b64encode(buf.getvalue()).decode()
 parts.append(f'<details class="proof" id="{proof_ids[p]}"><summary>{esc(p.split("/")[-1])}</summary><figure><img loading="lazy" width="{im.width}" height="{im.height}" src="data:image/webp;base64,{encoded}" alt="App review capture: {esc(p.split("/")[-1])}"><figcaption>{esc(p)} · {im.width} × {im.height}px</figcaption></figure></details>')
parts.append('''<p class="footer small">Assessment only. Application behavior was not changed during this pass. The machine-readable scorecard and supplemental capture script accompany this report.</p></main><script>function reveal(){const id=decodeURIComponent(location.hash.slice(1));const el=document.getElementById(id);if(el?.tagName==='DETAILS'){el.open=true;el.scrollIntoView()}}addEventListener('hashchange',reveal);reveal()</script></body></html>''')
out=data_path.with_suffix('.html');out.write_text(''.join(parts));print(f'{out}: {out.stat().st_size/1024/1024:.2f} MiB, {len(proof)} embedded screenshots')
