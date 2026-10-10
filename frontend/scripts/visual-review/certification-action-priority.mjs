import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Original module controls with synthetic validation states. No completion, grading, provisioning or provider writes.' })
const { page, context } = review
const exercise = JSON.parse(await readFile(new URL('../../../backend/certification-data/exercises.json', import.meta.url), 'utf8')).foundations
let state = 'unchecked'
const writes = []
let validationRequests = 0
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/progress')) return route.fulfill({ json: { id: 'action-priority', user_id: 'reviewer', modules: {
    foundations: { completed: false, stars: 0, attempts: 0, provisioned_docs: exercise.documents.map((_, index) => `sample-${index}`) },
  }, total_xp: 0, level: 'novice', certified: false, certified_at: null } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: exercise })
  if (path.endsWith('/lab-status')) return route.fulfill({ json: { module_id: 'foundations', state: 'ready', credit_changed: false, folder_id: 'lab', folder_name: 'Synthetic assigned lab',
    documents: exercise.documents.map((name, index) => ({ name, state: 'ready', document_id: `sample-${index}` })) } })
  if (path.endsWith('/validate')) {
    assert.equal(request.method(), 'POST')
    validationRequests++
    if (state === 'unavailable') return route.fulfill({ status: 503, json: { detail: 'Synthetic check unavailable' } })
    return route.fulfill({ json: { module_id: 'foundations', passed: state === 'passed', stars: state === 'passed' ? 1 : 0,
      checks: [{ name: 'Required saved work', passed: state === 'passed', detail: 'Synthetic requirement check', role: 'required' }] } })
  }
  if (request.method() !== 'GET') writes.push({ path, method: request.method() })
  return route.fallback()
})
const baseline = process.env.REVIEW_BASELINE === '1'
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  await page.setViewportSize({ width: native ? 640 : 390, height: native ? 1688 : 844 })
  await page.goto(review.baseURL + '/certification')
  if (native) await review.setBrowserZoom(2)
  const panel = page.locator('[data-cert-panel]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await panel.getByRole('button', { name: /^1 Foundations/ }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  const check = panel.getByRole('button', { name: 'Check Progress', exact: true })
  const complete = panel.getByRole('button', { name: 'Complete Module', exact: true })
  for (state of ['unchecked', 'failed', 'passed', 'unavailable']) {
    if (state !== 'unchecked') {
      await check.click()
      if (state === 'unavailable') await panel.getByText('Recheck unavailable. These are previous check results; your earlier feedback is preserved.', { exact: true }).waitFor()
      else await panel.getByText(state === 'passed' ? 'All checks passed' : 'Some objectives remaining', { exact: true }).waitFor()
    }
    await complete.scrollIntoViewIfNeeded()
    const colors = { check: await check.evaluate(el => getComputedStyle(el).backgroundColor), complete: await complete.evaluate(el => getComputedStyle(el).backgroundColor) }
    review.observations.push({ state, colors, completionStillAvailable: await complete.isEnabled() })
    await review.capture(`actions-${state}`)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/actions-${state}.axe.json`, 'utf8')), [])
    assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
    for (const action of [check, complete]) assert.equal(await action.evaluate(el => {
      const r = el.getBoundingClientRect()
      return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
    }), true, `${state}: both actions remain visible`)
    if (!baseline) {
      if (state === 'failed') await panel.getByText('Review the remaining checks below, update your work, then check progress again.', { exact: true }).waitFor()
      if (state === 'unavailable') await panel.getByText('Your last feedback is preserved. Try Check Progress again to confirm the current requirements.', { exact: true }).waitFor()
      assert.notEqual(state === 'passed' ? colors.complete : colors.check, 'rgb(255, 255, 255)')
      assert.equal(state === 'passed' ? colors.check : colors.complete, 'rgb(255, 255, 255)')
      assert.equal(await complete.isEnabled(), true)
    }
    if (baseline) break
  }
  assert.deepEqual(writes, [])
  assert.equal(validationRequests, baseline ? 0 : 3)
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
