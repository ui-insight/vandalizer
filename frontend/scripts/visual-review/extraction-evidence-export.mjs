import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow, docs } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
await page.route('**/api/workflows/workflow-1',r=>r.fulfill({json:{...workflow,steps:[{id:'review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'prompt',name:'Prompt',data:{prompt:'Summarize the proposal.'}}]}]}}))
await page.route('**/api/workflows/workflow-1/validation-plan',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/validation-plan/generate',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/quality-history*',r=>r.fulfill({json:{history:[]}}))
await page.route('**/api/extractions/search-sets/item-1/quality-status*',r=>r.fulfill({json:{status:'unvalidated'}}))
await page.route('**/api/extractions/search-sets/item-1/quality-history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/search-sets/item-1/cross-field-rules',r=>r.fulfill({json:{rules:[]}}))
await page.route('**/api/workflows/workflow-1/validation-inputs',r=>r.fulfill({json:{inputs:[{id:'input-1',type:'text',text:'Budget: 200',label:'Proposal example'}]}}))
await page.route('**/api/workflows/workflow-1/expected-outputs',r=>r.fulfill({json:{expected_outputs:[{id:'expected-1',type:'expected_output',label:'Proposal summary with budget',output_text:'The budget is 200.',source:'manual'}]}}))
await page.route('**/api/extractions/test-cases?*',r=>r.fulfill({json:[{uuid:'test-1',search_set_uuid:'item-1',label:'Proposal example with budget',source_type:'text',source_text:'Budget: 200',expected_values:{Budget:'200'},user_id:'reviewer',created_at:'2026-09-24T00:00:00Z'}]}))
await page.route('**/api/extractions/search-sets/item-1',r=>r.fulfill({json:{id:'item-1',uuid:'item-1',title:'Budget compliance extraction',set_type:'extraction',user_id:'reviewer',extraction_config:{},created_at:'',updated_at:''}}))
await page.route('**/api/extractions/search-sets/item-1/items',r=>r.fulfill({json:[{id:'field-1',uuid:'field-1',search_set_uuid:'item-1',searchphrase:'Budget',title:'Budget',searchtype:'text',enum_values:[],is_optional:false,description:'The total budget'}]}))
await page.route('**/api/extractions/search-sets/item-1/history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/search-sets/item-1/quality-sparkline*',r=>r.fulfill({json:{scores:[]}}))
await page.route('**/api/extractions/search-sets/item-1/baseline-probe',r=>r.fulfill({json:{no_settings_score:0.5,num_cases_judged:1,sample_case_ids:['test-1'],tokens_used:200,duration_ms:30}}))
await page.route('**/api/extractions/search-sets/item-1/optimize?*',r=>r.fulfill({json:{items:new URL(r.request().url()).searchParams.get('limit')==='1'?[]:[{uuid:'previous-1',status:'completed',started_at:'2026-09-29T10:00:00Z',num_trials:8,optimized_score:0.84,baseline_default_score:0.52,judge_model:'Review model',options:{}}],count:1,skip:0,limit:20}}))

const values = [{ Deadline: '2026-10-15', Budget: '$125,000.50', Investigator: 'Jordan "Lee", PhD', Currency: null }, { Deadline: '2026-09-01', Budget: '$250,000.00', Investigator: 'Alex Morgan' }]
const fieldNames = ['Deadline', 'Budget', 'Investigator', 'Currency']
const source = (doc, quote, page, overrides = {}) => ({ document_uuid: doc.uuid, document_title: doc.title, quote, page, verified: true, value_supported: true, support: 'supported', ...overrides })
const sources = [{ Deadline: source(docs[0], 'Applications are due 2026-10-15.', 2, { page_approximate: true }), Budget: source(docs[0], 'The direct budget is $100,000.', 3, { value_supported: false, support: 'quote_unsupported' }), Investigator: source(docs[0], null, null, { verified: false, value_supported: null, support: 'unverified' }) }, { Deadline: source(docs[1], 'Applications are due 2026-09-01.', 1), Budget: source(docs[1], 'Total budget: $250,000.00.', 1), Investigator: source(docs[1], 'Alex Morgan leads the team.', 2, { value_supported: null, support: 'unassessed' }) }]
let runs = []
await page.route('**/api/extractions/search-sets/item-1/items', r => r.fulfill({ json: fieldNames.map((name, i) => ({ id: 'field-' + i, uuid: 'field-' + i, search_set_uuid: 'item-1', searchphrase: name, title: name, searchtype: 'text', enum_values: [], is_optional: false })) }))
await page.route('**/api/files/download?*', r => r.fulfill({ contentType: 'text/plain', body: 'Applications are due 2026-10-15. The direct budget is $100,000.' }))
await page.route('**/api/documents/poll_status*', r => r.fulfill({ json: { status: 'SUCCESS', complete: true, valid: true, processing: false, raw_text: 'Applications are due 2026-10-15. The direct budget is $100,000.', title: docs[0].title } }))
await page.route('**/api/extractions/run-sync', r => {
  runs.push(r.request().postDataJSON())
  return r.fulfill({ json: { results: values, sources, document_warnings: [{ document_uuid: 'doc-0', title: docs[0].title, codes: ['partial_ocr'], text: 'Only the first 30 pages could be read.' }], cross_field_sets: [{ results: [{ rule_id: 'deadline-order', status: 'fail', passed: false, message: 'The deadline precedes the start of the application window.' }], summary: { pass: 0, fail: 1, unparseable: 0, total: 1, pass_rate: 0, violation_rate: 1 } }, { results: [{ rule_id: 'budget', status: 'unparseable', passed: false, message: 'No total available for comparison.' }], summary: { pass: 0, fail: 0, unparseable: 1, total: 1, pass_rate: null, violation_rate: 0 } }] } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  if (await page.getByRole('region', { name: 'Tools and assistant', exact: true }).count()) assert.ok(await page.getByRole('region', { name: 'Tools and assistant', exact: true }).evaluate(e => e.scrollWidth <= e.clientWidth + 1 && e.scrollLeft === 0), id + ': tool content must not scroll sideways')
  console.log('Captured ' + id)
}
async function download(name) {
  await page.getByRole('button', { name: 'Export', exact: true }).click()
  const event = page.waitForEvent('download'); await page.getByRole('menuitem', { name, exact: true }).click()
  const artifact = await event; return readFile(await artifact.path(), 'utf8')
}
try {
  for (const width of [320, 1440]) {
    runs = []
    await page.setViewportSize({ width, height: width === 320 ? 700 : 1000 }); await page.goto(review.baseURL + '/?mode=files')
    for (const name of [docs[0].title, docs[1].title]) await page.getByRole('checkbox', { name: 'Select ' + name, exact: true }).check()
    await page.getByRole('button', { name: /^(?:Open )?Library(?: panel)?$/ }).click(); await page.getByRole('button', { name: 'Open Budget compliance extraction', exact: true }).click(); await page.getByRole('button', { name: 'RUN', exact: true }).click()
    await page.getByText('$125,000.50', { exact: true }).waitFor(); assert.deepEqual(runs[0].document_uuids, ['doc-0', 'doc-1'])
    const first = page.getByRole('radio', { name: 'Document 1: ' + docs[0].title, exact: true }), second = page.getByRole('radio', { name: 'Document 2: ' + docs[1].title, exact: true })
    await first.scrollIntoViewIfNeeded(); await shot('extraction-document-identity-' + width)
    await page.getByText('Only the first 30 pages could be read.', { exact: false }).waitFor(); await page.getByText('1 of 1 cross-field check failed', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Inspect source for Deadline', exact: true }).getByText('p. ~2', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Inspect source for Budget', exact: true }).getByText(/unconfirmed/).waitFor()
    await page.getByRole('button', { name: 'Inspect source for Investigator', exact: true }).getByText('no source', { exact: true }).waitFor()
    await page.getByText('No confirmed value. Check the source; this does not establish that the information is absent.', { exact: true }).scrollIntoViewIfNeeded(); await shot('extraction-missing-unconfirmed-' + width)
    await first.focus(); await page.keyboard.press('ArrowRight'); assert.equal(await second.getAttribute('aria-checked'), 'true'); assert.equal(await second.evaluate(e => document.activeElement === e), true)
    await page.getByText('$250,000.00', { exact: true }).waitFor(); await page.getByText('No cross-field check could be evaluated on these values', { exact: false }).waitFor()
    await page.getByText('No value returned for this field. Check the source.', { exact: true }).scrollIntoViewIfNeeded(); await shot('extraction-second-document-' + width)
    const csv = await download('Download CSV')
    assert.equal(csv, '"Document","Deadline","Budget","Investigator","Currency"\n"Proposal narrative.pdf","2026-10-15","$125,000.50","Jordan ""Lee"", PhD","N/A"\n"Budget justification.docx","2026-09-01","$250,000.00","Alex Morgan",""\n')
    const json = JSON.parse(await download('Download JSON'))
    assert.deepEqual(json, [{ document: docs[0].title, values: { ...values[0], Currency: 'N/A' } }, { document: docs[1].title, values: values[1] }])
    await page.getByText(/CSV, JSON and clipboard exports contain values only/).scrollIntoViewIfNeeded(); await shot('extraction-export-scope-' + width)
    await first.click(); await page.getByRole('button', { name: 'Inspect source for Budget', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Files panel', exact: true }).click()
    await page.getByRole('heading', { name: docs[0].title, exact: true }).waitFor(); await page.getByText('Applications are due 2026-10-15. The direct budget is $100,000.', { exact: false }).first().waitFor(); await shot('extraction-inspect-original-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Synthetic two-document dates/money/quotes/commas/null/omitted fields: named keyboard result selection, partial input warning, failed and unevaluated cross-field checks, located/approximate/unconfirmed/missing evidence, original inspection, exact CSV/JSON value and document identity comparison. Export source-reference absence disclosed. No model accuracy claim.')
} catch (error) { await review.capture('extraction-evidence-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
