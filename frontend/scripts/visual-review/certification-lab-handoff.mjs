import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
import { workflow, docs } from './fixtures.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const exercises = JSON.parse(await readFile(new URL('exercises.json', data), 'utf8'))
const sourcePdf = await readFile(new URL('documents/budget-justification.pdf', data))

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5305', evidenceMode: 'Actual production frontend; synthetic existing workflow/extraction and source fixtures. Lab-to-Files handoff preserves unsent editor/chat drafts, selected source and mounted DOM. All course writes intercepted; no execution or grading.' })
const { page, context } = review
const writes = []
await context.route('**/api/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (req.method() !== 'GET' && req.method() !== 'HEAD') writes.push({ method: req.method(), path })
  if (path === '/api/documents/list') return route.fulfill({ json: { folders: [], documents: docs.map((doc, index) => index === 0 ? { ...doc, title: 'Budget justification.pdf' } : doc) } })
  if (path === '/api/files/download') return route.fulfill({ contentType: 'application/pdf', headers: { 'Content-Length': String(sourcePdf.length) }, body: req.method() === 'HEAD' ? undefined : sourcePdf })
  if (path === '/api/auth/config') return route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } })
  if (path === '/api/certification/modules/foundations/exercise') return route.fulfill({ json: exercises.foundations })
  if (path === '/api/certification/modules/foundations/lab-status') return route.fulfill({ json: {
    module_id: 'foundations', state: 'not_setup', documents: [], folder_id: null, folder_name: null, credit_changed: false,
  } })
  if (path === '/api/workflows/workflow-1') return route.fulfill({ json: { ...workflow, input_config: { trigger_type: 'text_input' } } })
  if (path === '/api/library/items/item-1/touch') return route.fulfill({ json: { ok: true } })
  if (path.startsWith('/api/extractions/search-sets/extraction-1')) {
    const suffix = path.slice('/api/extractions/search-sets/extraction-1'.length)
    const json = suffix === '' ? { id: 'extraction-1', uuid: 'extraction-1', title: 'Budget compliance extraction', set_type: 'extraction', user_id: 'reviewer', extraction_config: {}, created_at: '', updated_at: '' }
      : suffix === '/items' ? [{ id: 'field-1', uuid: 'field-1', search_set_uuid: 'extraction-1', searchphrase: 'Budget', title: 'Budget', searchtype: 'text', enum_values: [], is_optional: false }]
        : suffix === '/quality-status' ? { status: 'unvalidated' }
          : suffix === '/quality-sparkline' ? { scores: [] }
            : suffix === '/cross-field-rules' ? { rules: [] }
              : ['/history', '/quality-history'].includes(suffix) ? { runs: [] } : null
    if (json !== null) return route.fulfill({ json })
  }
  if (path === '/api/extractions/test-cases') return route.fulfill({ json: [] })
  return route.fallback()
})
const panel = page.locator('[data-cert-panel]')
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const baseline = process.env.REVIEW_HANDOFF_BASELINE === '1'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780, 2048] : [320, 1024, 1440]) {
    await page.setViewportSize({ width, height: native ? 1800 : 1000 })
    for (const tool of width < 1024 ? ['chat'] : ['workflow', 'extraction', ...(width === 1440 ? ['chat'] : [])]) {
      const query = tool === 'chat' ? 'mode=chat&tab=assistant' : `mode=files&tab=library&${tool}=${tool === 'workflow' ? 'workflow-1' : 'extraction-1'}`
      await page.goto(`${review.baseURL}/?${query}`)
      if (native) await review.setBrowserZoom(2)
      const draft = page.getByRole('textbox', { name: tool === 'workflow' ? 'Text to process' : tool === 'extraction' ? 'Add term to extract' : 'Message input', exact: true })
      const value = `Unsent ${tool} draft — keep this while I check my lab files.`
      await draft.fill(value)
      const original = await draft.elementHandle()
      await page.evaluate(() => { window.certificationHandoffSentinel = 'same-mounted-page' })
      const selected = tool === 'chat' ? null : page.getByRole('checkbox', { name: 'Select Budget justification.pdf', exact: true })
      if (selected) await selected.check()
      const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
      if (!await opener.isVisible()) {
        await page.getByRole('button', { name: 'Open activity', exact: true }).click()
      }
      await opener.focus(); await page.keyboard.press('Enter')
      if (!await panel.getByRole('heading', { name: 'Module 1: Foundations', exact: true }).count()) {
        await panel.getByRole('button', { name: /^1 Foundations/ }).click()
      }
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const lab = panel.getByRole('region', { name: 'Course sample files', exact: true })
      await lab.getByRole('button', { name: 'Set Up Lab', exact: true }).waitFor()
      const handoff = baseline ? lab.getByRole('link', { name: 'Open Workspace', exact: true }) : lab.getByRole('button', { name: 'Open Files in workspace', exact: true })
      await handoff.focus()
      await capture(`${tool}-handoff-${width}`)
      await page.keyboard.press('Enter')
      await panel.waitFor({ state: 'hidden' })
      assert.equal(await page.evaluate(() => window.certificationHandoffSentinel), 'same-mounted-page', 'The lab handoff must not reload the application')
      assert.equal(await original.evaluate(element => element.isConnected), true, 'The original draft input must remain mounted')
      assert.equal(await original.evaluate(element => element.value), value)
      assert.equal(new URL(page.url()).searchParams.get('mode'), 'files')
      if (selected) assert.equal(await selected.isChecked(), true)
      if (tool !== 'chat') {
        assert.equal(new URL(page.url()).searchParams.get(tool), tool === 'workflow' ? 'workflow-1' : 'extraction-1')
        await draft.scrollIntoViewIfNeeded()
      }
      await capture(`${tool}-preserved-${width}`)
      if (tool === 'chat') {
        await page.getByRole('navigation', { name: 'Workspace navigation', exact: true }).getByRole('button', { name: 'Chat', exact: true }).click()
        assert.equal(await draft.inputValue(), value)
        await capture(`chat-resumed-${width}`)
      }
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
  review.observations.push({ mountedDraftsRetained: true, selectedDocumentsRetained: true, fullPageReloads: 0, courseWrites: 0, modelRequests: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
