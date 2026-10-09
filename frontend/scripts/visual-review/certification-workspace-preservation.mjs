import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
import { workflow, docs } from './fixtures.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const exercises = JSON.parse(await readFile(new URL('exercises.json', data), 'utf8'))
const sourcePdf = await readFile(new URL('documents/budget-justification.pdf', data))

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual production frontend; synthetic existing workflow/extraction and source fixtures. Unsubmitted editor drafts and document selection; no execution or grading.' })
const { page, context } = review
const writes = []
await context.route('**/api/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (req.method() !== 'GET' && req.method() !== 'HEAD') writes.push({ method: req.method(), path })
  if (path === '/api/documents/list') return route.fulfill({ json: { folders: [], documents: docs.map((doc, index) => index === 0 ? { ...doc, title: 'Budget justification.pdf' } : doc) } })
  if (path === '/api/files/download') return route.fulfill({ contentType: 'application/pdf', headers: { 'Content-Length': String(sourcePdf.length) }, body: req.method() === 'HEAD' ? undefined : sourcePdf })
  if (path === '/api/certification/modules/ai_literacy/exercise') return route.fulfill({ json: exercises.ai_literacy })
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
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of [1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const tool of ['workflow', 'extraction']) {
      await page.goto(`${review.baseURL}/?mode=files&tab=library&${tool}=${tool === 'workflow' ? 'workflow-1' : 'extraction-1'}`)
      const draft = page.getByRole('textbox', { name: tool === 'workflow' ? 'Text to process' : 'Add term to extract', exact: true })
      const value = tool === 'workflow' ? 'My unsent proposal review input — preserve the source and budget caveat.' : 'Unsubmitted learner field'
      await draft.fill(value)
      const selected = page.getByRole('checkbox', { name: 'Select Budget justification.pdf', exact: true })
      await selected.check()
      const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
      await opener.focus(); await page.keyboard.press('Enter')
      await panel.getByRole('button', { name: /^0 AI Literacy/ }).click()
      for (const mode of ['docked-left', 'docked-right', 'floating', 'docked-bottom', 'fullscreen']) {
        await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption(mode)
        await capture(`${tool}-${mode}-${width}`)
        assert.equal(await draft.inputValue(), value)
        assert.equal(await selected.isChecked(), true)
      }
      await page.getByRole('button', { name: 'Return to workspace', exact: true }).focus()
      await page.keyboard.press('Escape'); await panel.waitFor({ state: 'hidden' })
      assert.equal(await draft.inputValue(), value)
      assert.equal(await selected.isChecked(), true)
      await draft.scrollIntoViewIfNeeded()
      await capture(`${tool}-draft-preserved-${width}`)
      await page.getByRole('row', { name: 'Document: Budget justification.pdf', exact: true }).click()
      await page.locator('canvas').first().waitFor()
      const originalCanvas = await page.locator('canvas').first().elementHandle()
      await opener.click()
      await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('docked-right')
      await capture(`${tool}-source-and-lesson-${width}`)
      await page.getByRole('button', { name: 'Return to workspace', exact: true }).click()
      assert.equal(await originalCanvas.evaluate(el => el.isConnected), true, 'Opening the course must retain the current rendered source')
      assert.equal(await draft.inputValue(), value)
      await page.getByRole('button', { name: 'Close document', exact: true }).click()
      assert.equal(await selected.isChecked(), true)
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual([...review.unmatched], []); assert.deepEqual(review.errors, [])
  review.observations.push({ editorDraftsPreserved: true, documentSelectionPreserved: true, courseModes: 5, widths: [1024, 1440], executions: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
