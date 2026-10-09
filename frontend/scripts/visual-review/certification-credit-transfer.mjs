import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_TRANSFER_FIXTURE, 'utf8'))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  resetStorage: false, evidenceMode: 'Committed frontend; real disposable-persistence transfer payloads with synthetic API delivery and a lost POST response. No actual learner changes or grading.' })
const { page, context } = review
let applied = false
const writes = [], receipts = []
function course() { return { ...(applied ? fixture.after_course : fixture.before_course), versioned: true } }
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() })
  if (path.endsWith('/course')) return route.fulfill({ json: course() })
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...course(), ...course().progress } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: course().enrollment_id, pending: null } })
  if (path.endsWith('/saved-course-options')) return route.fulfill({ json: fixture.options })
  if (path.endsWith('/credit-transfer-preview')) return route.fulfill({ json: fixture.preview })
  if (path.endsWith('/credit-transfers') && request.method() === 'POST') {
    assert.deepEqual(request.postDataJSON(), fixture.request)
    assert.equal(applied, false, 'Credit cannot be submitted twice')
    applied = true
    return route.abort('failed')
  }
  if (path.endsWith('/credit-transfers/' + fixture.request.request_id)) {
    assert.ok(applied)
    receipts.push(path)
    return route.fulfill({ json: fixture.receipt })
  }
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1), box = await target.boundingBox()
  assert.equal(shot.pageWidth, shot.viewport.width)
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
  console.log(id)
}
async function openChoices() {
  const panel = page.locator('[data-cert-panel]')
  await page.getByRole('button', { name: 'Open course without chat', exact: true }).click()
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  const summary = panel.getByText('Course progress and credential', { exact: true })
  await summary.focus(); await page.keyboard.press('Enter')
  await panel.getByRole('button', { name: 'Choose a saved course', exact: true }).click()
  const transfer = panel.getByRole('region', { name: 'Credit from your original course', exact: true })
  await transfer.waitFor()
  return { panel, transfer }
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    applied = false
    const initialWrites = writes.length, initialReads = receipts.length
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    await page.goto(review.baseURL + '/')
    if (native) await review.setBrowserZoom(2)
    let { panel, transfer } = await openChoices()
    await transfer.getByRole('button', { name: 'Review credit eligibility', exact: true }).click()
    await transfer.getByRole('button', { name: 'Review transfer: AI Literacy', exact: true }).click()
    const submit = transfer.getByRole('button', { name: 'Transfer reviewed credit', exact: true })
    assert.equal(await submit.isEnabled(), false)
    assert.equal(writes.length, initialWrites)
    await capture(`transfer-review-${width}`, transfer.getByText('Transfer credit for AI Literacy', { exact: true }))
    const consent = transfer.getByRole('checkbox')
    await consent.focus(); await page.keyboard.press('Space')
    assert.equal(await submit.isEnabled(), true)
    await submit.focus(); await page.keyboard.press('Enter')
    await transfer.getByRole('button', { name: 'Check saved transfer', exact: true }).waitFor()
    await capture(`transfer-uncertain-${width}`, transfer.getByRole('status'))
    assert.equal(writes.length, initialWrites + 1)
    await page.reload()
    ;({ panel, transfer } = await openChoices())
    const check = transfer.getByRole('button', { name: 'Check saved transfer', exact: true })
    await check.waitFor()
    assert.equal(writes.length, initialWrites + 1, 'Reopening cannot submit another transfer')
    await check.focus(); await page.keyboard.press('Enter')
    await transfer.getByText(/credit recorded, with 50 XP carried into this course and 0 new XP earned/).waitFor()
    assert.equal(writes.length, initialWrites + 1)
    assert.equal(receipts.length, initialReads + 1)
    await capture(`transfer-recovered-${width}`, transfer.getByRole('status'))
    await panel.getByText('50 XP toward this course', { exact: false }).waitFor()
    await capture(`transfer-course-progress-${width}`, panel.getByText('50 XP toward this course', { exact: false }))
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ writes, savedReceiptReads: receipts.length, consentRequired: true,
    recoveredAcrossReload: true, duplicateWrites: 0, xpCarried: 50, newXpEarned: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
