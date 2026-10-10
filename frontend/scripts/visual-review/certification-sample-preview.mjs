import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const exercises = JSON.parse(await readFile('../backend/certification-data/exercises.json', 'utf8'))
const filename = exercises.foundations.documents[0]
const pdf = await readFile(`../backend/certification-data/documents/${filename}`)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5305',
  evidenceMode: 'Frozen frontend and actual authored NSF PDF bytes. Synthetic assigned-source/read-permission responses; all API writes intercepted. Course/chat retention, access recheck and modal keyboard return. No live learner, ingestion, grading or model calls.' })
const { page, context } = review
const touch = process.env.REVIEW_TOUCH === '1'
const activate = locator => touch ? locator.tap() : locator.click()
const progress = { id: 'sample-preview', user_id: 'reviewer', modules: { foundations: { provisioned_docs: ['sample'] } }, total_xp: 0, level: 'novice', certified: false, certified_at: null }
let available = true, denyDownload = false, reads = 0, fileReads = 0
const writes = []
await context.route('**/api/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (!['GET', 'HEAD'].includes(request.method())) writes.push({ path, method: request.method() })
  if (path === '/api/auth/config') return route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } })
  if (path === '/api/files/download' && url.searchParams.get('docid') === 'sample') {
    fileReads++
    if (denyDownload) return route.fulfill({ status: 404, json: { detail: 'Synthetic file access revoked after status read' } })
    return route.fulfill({ status: 200, headers: { 'content-type': 'application/pdf', 'content-length': String(pdf.length), 'content-disposition': `inline; filename="${filename}"` }, body: request.method() === 'HEAD' ? '' : pdf })
  }
  if (path === '/api/documents/poll_status' && url.searchParams.get('docid') === 'sample') return route.fulfill({ json: { uuid: 'sample', status: 'complete', processing: false, valid: true } })
  if (path.startsWith('/api/certification/')) {
    assert.equal(request.method(), 'GET')
    if (path.endsWith('/progress')) return route.fulfill({ json: progress })
    if (path.endsWith('/modules/foundations/exercise')) return route.fulfill({ json: exercises.foundations })
    if (path.endsWith('/modules/foundations/lab-status')) {
      reads++
      return route.fulfill({ json: { module_id: 'foundations', state: available ? 'ready' : 'unavailable', credit_changed: false,
        folder_id: 'lab', folder_name: 'Certification Lab', documents: [{ name: filename, document_id: available ? 'sample' : null, state: available ? 'ready' : 'unavailable' }] } })
    }
  }
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : touch ? [320] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1300 : 650 })
    available = true; denyDownload = false
    await page.goto(review.baseURL + '/?mode=chat&tab=assistant')
    if (native) await review.setBrowserZoom(2)
    const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
    await draft.fill('Keep my question while I inspect the assigned sample.')
    const originalDraft = await draft.elementHandle()
    await page.evaluate(() => { window.courseSampleSentinel = 'original-course' })
    const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
    if (!await opener.isVisible()) await activate(page.getByRole('button', { name: 'Open activity', exact: true }))
    await activate(opener)
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await activate(panel.getByRole('button', { name: /^1 Foundations/ }))
    const source = panel.getByRole('button', { name: `View assigned ${filename}`, exact: true })
    await source.scrollIntoViewIfNeeded(); await source.focus()
    await capture(`assigned-sample-${width}`)
    if (touch) await activate(source); else await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: `Assigned sample: ${filename}`, exact: true })
    const back = dialog.getByRole('button', { name: 'Return to course', exact: true })
    await dialog.locator('canvas').first().waitFor({ state: 'visible' })
    assert.equal(await back.evaluate(el => el === document.activeElement), true)
    await capture(`sample-pdf-${width}`)
    await page.keyboard.press('Shift+Tab')
    assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true)
    await page.keyboard.press('Tab')
    assert.equal(await back.evaluate(el => el === document.activeElement), true)
    if (touch) await activate(back); else await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'detached' })
    assert.equal(await source.evaluate(el => el === document.activeElement), true)
    assert.equal(await panel.isVisible(), true)
    available = false
    const beforeDenied = fileReads
    await activate(source)
    await dialog.getByRole('alert').waitFor()
    assert.equal(fileReads, beforeDenied)
    await capture(`sample-access-unavailable-${width}`)
    available = true; denyDownload = true
    await activate(dialog.getByRole('button', { name: 'Check sample access again', exact: true }))
    await dialog.getByRole('heading', { name: 'Source unavailable', exact: true }).waitFor()
    await capture(`sample-file-revoked-${width}`)
    assert.equal(await dialog.getByText(/Return to your course and check sample status/).count(), 1)
    await activate(back)
    await dialog.waitFor({ state: 'detached' })
    assert.equal(await source.evaluate(el => el === document.activeElement), true)
    assert.equal(await originalDraft.evaluate(el => el.isConnected && el.value.startsWith('Keep my question')), true)
    assert.equal(await page.evaluate(() => window.courseSampleSentinel), 'original-course')
    await capture(`course-after-sample-${width}`)
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ reads, fileReads, courseAndChatRetained: true, keyboardModalReturnVerified: true, currentAccessRechecked: true, apiWrites: 0,
    authoredPdf: { filename, bytes: pdf.length, sha256: createHash('sha256').update(pdf).digest('hex') } })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
