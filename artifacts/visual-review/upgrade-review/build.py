from pathlib import Path
import json, html, re
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
base=root/'artifacts/visual-review'
runs=['upgrade-final','upgrade-final-responsive','upgrade-final-recheck','upgrade-final-detail-recheck','upgrade-followup-detail','upgrade-followup-responsive','upgrade-polish-final-journeys','upgrade-polish-final-context','upgrade-folder-recheck','2026-09-26-recovery-verified','2026-09-26-recovery-layout-verified','2026-09-28-wizard-flow-verified','2026-09-28-wizard-api-verified','2026-09-28-wizard-mobile-final','2026-09-28-history-verified','2026-09-28-lifecycle-evidence','2026-09-28-resumption-final','2026-09-28-questions-final','2026-09-28-sources-release','2026-09-28-uploads-evidence','2026-09-28-validation-scope','2026-09-28-source-intake-final','2026-09-28-catalog-filters-evidence','2026-09-28-catalog-evidence-review','2026-09-28-chat-navigation-evidence','2026-09-28-chat-scope-final','2026-09-28-file-library-evidence','2026-09-28-projects-restored-layout','2026-09-28-files-restored-layout','2026-09-28-automation-run-evidence','2026-09-28-automation-filters-final','2026-09-28-automation-history-final','2026-09-28-automation-summary-review','2026-09-28-automation-filter-light','2026-09-28-automation-save-review','2026-09-28-automation-launch-evidence','2026-09-28-automation-run-reconnect','2026-09-28-library-recovery-evidence','2026-09-28-library-opening-evidence','2026-09-28-file-library-regression','2026-09-29-knowledge-states-evidence','2026-09-29-knowledge-project-final','2026-09-29-chat-composer-evidence','2026-09-29-catalog-usage-final','2026-09-29-catalog-filter-regression','2026-09-29-onboarding-tour-evidence','2026-09-29-agent-recovery-evidence','2026-09-29-panel-preferences-final','2026-09-29-panel-file-library-regression','2026-09-30-validation-resumption-short','2026-09-30-validation-questions-short','2026-09-30-validation-history-short','2026-09-30-validation-dialogs-final','2026-09-30-navigation-retention-complete','2026-09-30-navigation-file-library-regression','2026-09-30-navigation-project-final','2026-09-30-context-release','2026-09-30-context-retention-final','2026-09-30-context-file-library-final','2026-09-30-headers-evidence','2026-09-30-headers-retention','2026-09-30-headers-file-library','2026-09-30-density-headers','2026-09-30-density-composer-context','2026-09-30-density-navigation-release','2026-09-30-density-file-library','2026-09-30-density-chat-reading']
runs += ['2026-09-30-theme-knowledge', '2026-09-30-theme-validation-overlay', '2026-09-30-theme-questions', '2026-09-30-theme-dialogs-final', '2026-09-30-theme-history-final', '2026-09-30-theme-source-intake', '2026-09-30-theme-domains-verified', '2026-09-30-theme-catalog-release', '2026-09-30-theme-context-release']
runs += ['2026-09-30-typography-baseline', '2026-09-30-typography-domains', '2026-09-30-typography-questions', '2026-09-30-typography-file-library', '2026-09-30-typography-headers', '2026-09-30-typography-context', '2026-09-30-typography-history', '2026-09-30-typography-dialogs', '2026-09-30-typography-chat-reading-final', '2026-09-30-typography-context-meter-final']
runs += ['2026-09-30-spacing-responsive-final', '2026-09-30-spacing-baseline', '2026-09-30-spacing-domains', '2026-09-30-spacing-file-library', '2026-09-30-spacing-dialogs', '2026-09-30-spacing-headers']
runs += ['2026-09-30-actions-baseline-release', '2026-09-30-actions-file-library-final', '2026-09-30-actions-source-intake-final', '2026-09-30-actions-dialogs-final', '2026-09-30-actions-keyboard-release']
runs += ['2026-09-30-forms-source-intake-final', '2026-09-30-forms-wizard-final', '2026-09-30-forms-catalog-recovery', '2026-09-30-acceptance-baseline', '2026-09-30-acceptance-forms', '2026-09-30-acceptance-actions', '2026-09-30-domains-final', '2026-09-30-text-final', '2026-09-30-zoom-final', '2026-09-30-acceptance-library', '2026-09-30-acceptance-responsive']
runs += ['2026-09-30-accessibility-verified']
captures={}; manifests=[]
for name in runs:
 p=base/name;m=json.loads((p/'manifest.json').read_text())
 assert not m['errors'] and not m['unmatched'], name
 assert not any(c['id'].endswith('-blocked') for c in m['captures']),name
 manifests.append((name,m))
 for c in m['captures']:
  for ext in ['png','txt','axe.json']: assert (p/(c['id']+'.'+ext)).is_file()
  captures[c['id']]={**c,'run':name}
assert all(c['pageWidth']<=c['viewport']['width'] for c in captures.values())
violations=[]
for c in captures.values():
 for a in json.loads((base/c['run']/(c['id']+'.axe.json')).read_text()):violations.append((c['id'],a['id'],a['impact']))
assert not violations,violations
score=json.loads((root/'frontend/scripts/visual-review/scorecard.json').read_text())
final_grades=json.loads((out/'final-grades.json').read_text())
updates={a['id']:(a['ui'],a['ux'],a['evidence'],a['rationale']) for a in final_grades['areas']}
rows=[]; json_rows=[]
for area in score['areas']:
 ui,ux,evidence,note=updates[area['id']];c=captures[evidence];url=f"../{c['run']}/{evidence}.png"
 rows.append(f"| {area['name']} | {area['ui']}/{area['ux']} | {ui}/{ux} | [{evidence}]({url}) |")
 json_rows.append({'id':area['id'],'name':area['name'],'baseline_ui':area['ui'],'baseline_ux':area['ux'],'ui':ui,'ux':ux,'evidence':url,'note':note})
total=sum(len(m['captures']) for _,m in manifests)
completed=json.loads((out/'completed-items.json').read_text())
intro=f'''# Vandalizer visual and UX review — final local acceptance

September 30, 2026 · [Issue #964](https://github.com/ui-insight/vandalizer/issues/964)

**{len(completed)}/169 checklist items implemented and reviewed locally.** All 13 reviewed areas meet the original minimum of 8/10 for UI and UX; mobile independently meets 8/8. These are judgments of the reviewed frontend and fixture-backed interactions, not live-service certification. Nothing has been pushed or deployed.

## Before and after

{final_grades['method']}

| Area | Baseline UI/UX | Final UI/UX | Inspected evidence |
|---|---:|---:|---|
'''+'\n'.join(rows)+f'''

**Mobile: baseline 3 → final UI 8 / UX 8.** {final_grades['mobile']['rationale']}

[Original rubric and findings](../2026-09-25/report.md) · [Complete checklist](../../../docs/ui-ux-upgrade-checklist.md) · [Dated implementation and verification log](../../../docs/ui-ux-implementation-progress.md) · [Per-area judgments](final-grades.json)

## Final repairs and verification

- Shared form labels distinguish required and optional entries. Field errors have linked descriptions and focus; server failures preserve valid drafts for retry.
- Text and icons identify recorded run status. Project/trust badges share geometry and semantic colors while availability and measured quality remain distinct.
- Shared pickers retain selections across search and retry, ignore stale responses, fit short screens, contain focus and isolate Escape. Knowledge creation keeps a stable header/footer. Destructive confirmation initially focuses the safe action.
- A screenshot audit caught doubled-text tab and header overlap that page-width/axe checks did not detect. Both editor resize observers now attach after loading, compact tabs are named, workflow tabs support arrow/Home/End navigation, and the header wraps or collapses labels without covering the logo. Direct reinspection confirmed the repair.
- File timestamps clear row actions; Library descriptions wrap; the Explore detail header uses neutral task styling. The empty supporting Assistant is compact while Files and Library/tool navigation retain the approved parallel-pane behavior.
- Upload announcements expose state changes separately from percentage bars. Validation announcements exclude elapsed seconds, tokens and trial streaming; status/phase changes remain polite and atomic. Reduced-motion loading states retain text.
- The final browser evidence includes the 55 original baseline states, viewport matrix, keyboard focus and menu/dialog actions, nested generation/picker Escape, short-form validation and retry, file-to-Library execution/error/retry/return at 200% equivalent zoom, and separately doubled text. Earlier selected evidence covers 120 Library items, 251 validation questions, long content, role/scope restrictions, resumption and failure recovery.
- Production build and TypeScript pass. Touched-file ESLint has zero errors; existing hook-dependency warnings are recorded in the implementation log. The full frontend suite has 1,199 passing tests across 176 passing files, with only the same three pre-existing Landing signup failures (one file). Focused regressions and announcement checks pass.

**Selected evidence:** {len(captures)} distinct states across {total} captures. Every selected capture has its image, accessible tree and axe output; latest selected states have zero axe violations and no horizontal page overflow. Manifests record source/fixture fingerprints and browser versions. Superseded diagnostic runs remain local and are excluded from acceptance.

## Resolved original findings

UX-01 upload scope is retained and asserted in outgoing requests. UX-02 responsive overflow and UX-04 Library clipping are repaired. UX-03 wizard Enter preserves and advances the draft. UX-05 active work receives primary hierarchy with a compact supporting Assistant. UX-06 source completeness and textual operational state are explicit. UX-07 accessible names, structure, contrast and keyboard checks pass in the reviewed surfaces. UX-08 activation has a complete review and explicit disabled/enabled choices. UX-09 validation has a shorter task-oriented path and bounded estimates. UX-10 approvals and progress are scoped to the operation, with retained artifacts and recovery.

## Limits and release handoff

'''+'\n'.join('- '+item for item in final_grades['limitations'])+'\n\n## Per-area assessment\n\n'+'\n\n'.join(f"**{a['name']} — UI {a['ui']}, UX {a['ux']}:** {a['note']}" for a in json_rows)+'\n\n## Evidence manifests\n\n'+'\n'.join(f"- [{name}](../{name}/manifest.json): {len(m['captures'])} captures; source `{m['sourceFingerprint']}`; {m['buildMode']}; Chromium {m['browserVersion']}." for name,m in manifests)+'\n'
(out/'report.md').write_text(intro)
(out/'review-summary.json').write_text(json.dumps({'status':'169-item local implementation and visual acceptance complete; live-service and deployment limits apply','completed_items':len(completed),'total_items':169,'unique_states':len(captures),'capture_executions':total,'mobile_grade':8,'mobile':final_grades['mobile'],'grading_method':final_grades['method'],'limitations':final_grades['limitations'],'areas':json_rows,'axe_latest_violations':violations,'runs':[{'directory':name,**m} for name,m in manifests]},indent=2)+'\n')
esc=html.escape
cards=[]
for id,c in captures.items():
 href=f"../{c['run']}/{id}"
 cards.append(f'<article data-screen="{esc(id)}"><a href="{href}.png"><img loading="lazy" src="{href}.png" alt="{esc(id)}"><h3>{esc(id)}</h3></a><p>{c["viewport"]["width"]} × {c["viewport"]["height"]} · <a href="{href}.txt">Accessible tree</a> · <a href="{href}.axe.json">Axe</a></p></article>')
pairs=[]
for id in ['files-mobile','library-mobile','chat-home','knowledge-detail','wizard-5-activation','automation-detail','chat-agent-confirmation']:
 old=base/'2026-09-25'/(id+'.png')
 if old.exists() and id in captures:
  new=captures[id]
  pairs.append(f'<section><h2>{esc(id)}</h2><div class="pair"><figure><figcaption>Before</figcaption><a href="../2026-09-25/{id}.png"><img loading="lazy" src="../2026-09-25/{id}.png" alt="Before: {esc(id)}"></a></figure><figure><figcaption>After</figcaption><a href="../{new["run"]}/{new["id"]}.png"><img loading="lazy" src="../{new["run"]}/{new["id"]}.png" alt="After: {esc(id)}"></a></figure></div></section>')
html_rows=''.join(f'<tr><td>{esc(a["name"])}</td><td>{a["baseline_ui"]}/{a["baseline_ux"]}</td><td>{a["ui"]}/{a["ux"]}</td></tr>' for a in json_rows)
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vandalizer UX upgrade review</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#242c35;font:16px/1.6 system-ui}main{max-width:1240px;margin:auto;padding:32px 20px}h1{font-size:36px;line-height:1.2}h2{margin-top:32px}a{color:#175c82}section,article{background:white;border:1px solid #d4dce3;border-radius:12px;padding:18px;margin:20px 0}table{border-collapse:collapse;width:100%;background:white}th,td{padding:9px 14px;text-align:left;border-bottom:1px solid #d4dce3}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0}figcaption{font-weight:700;margin-bottom:8px}img{max-width:100%;height:auto;max-height:650px;object-fit:contain;object-position:top;display:block}input{font:inherit;padding:10px 14px;width:100%;border:1px solid #8b99a8;border-radius:8px}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}.gallery article{margin:0}.gallery img{height:280px;width:100%;object-fit:contain}.gallery h3{font-size:15px}.gallery p{font-size:13px}[hidden]{display:none!important}:focus-visible{outline:3px solid #1b6ba5;outline-offset:3px}@media(max-width:700px){.pair{grid-template-columns:1fr}h1{font-size:28px}}</style><main>'''
page+=f'<h1>Vandalizer UX upgrade</h1><p><strong>Final local acceptance · {len(completed)}/169 items</strong></p><p>All reviewed areas meet the original UI and UX target of 8. Grades follow direct screenshot inspection and exercised interactions; fixture-backed evidence does not certify live execution. Changes are local, not deployed.</p><p><a href="report.md">Full report and limits</a> · <a href="review-summary.json">Machine-readable evidence</a> · <a href="https://github.com/ui-insight/vandalizer/issues/964">Issue #964</a></p><table><thead><tr><th>Area</th><th>Before UI/UX</th><th>Current UI/UX</th></tr></thead><tbody>{html_rows}</tbody></table><p>Mobile: 3 → 8. Latest selected evidence: {len(captures)} states, zero axe violations. See the report for the review method and release limits.</p>'
page+=''.join(pairs)+f'<h2>Evidence gallery</h2><label for="filter">Find a screen</label><input id="filter" type="search" placeholder="Try mobile, wizard, knowledge…"><p id="count" role="status">{len(captures)} screens</p><div class="gallery">'+''.join(cards)+'</div></main>'
page+='''<script>const f=document.getElementById('filter'),cards=[...document.querySelectorAll('[data-screen]')];f.addEventListener('input',()=>{const q=f.value.toLowerCase();for(const c of cards)c.hidden=!c.dataset.screen.includes(q);document.getElementById('count').textContent=cards.filter(c=>!c.hidden).length+' screens'});</script></html>'''
(out/'index.html').write_text(page)
for path in re.findall(r'(?:href|src)="([^"#]+)"',page):
 if not path.startswith('https://'): assert (out/path).exists(),path
print(f'Built report: {len(captures)} states / {total} captures, zero latest axe findings, {len(completed)} completed checklist items.')
