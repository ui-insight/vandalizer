import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const exercises = JSON.parse(await readFile('../backend/certification-data/exercises.json', 'utf8'))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5305',
  evidenceMode: 'Frozen production frontend; authored sample filenames and synthetic readiness/failure responses. All writes intercepted. Actual readiness and permissions verified separately in disposable MongoDB.' })
const { page, context } = review
const progress = { id: 'lab-status', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, unlocked: false }
let state = 'not_setup', failStatus = false, releasePreparation = null, writes = 0, reads = 0
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/modules/foundations/provision')) {
    assert.equal(request.method(), 'POST'); writes++
    await new Promise(resolve => { releasePreparation = resolve })
    state = 'processing'
    progress.modules.foundations = { provisioned_docs: ['sample'], completed: false, stars: 0, attempts: 0, xp_earned: 0 }
    return route.fulfill({ json: { provisioned_docs: ['sample'], folder_name: 'Certification Lab' } })
  }
  assert.equal(request.method(), 'GET')
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/modules/foundations/exercise')) return route.fulfill({ json: exercises.foundations })
  if (path.endsWith('/modules/foundations/lab-status')) {
    reads++
    if (failStatus) return route.fulfill({ status: 503, json: { detail: 'Synthetic status unavailable' } })
    return route.fulfill({ json: { module_id: 'foundations', state, credit_changed: false,
      folder_id: state === 'not_setup' ? null : 'lab', folder_name: state === 'not_setup' ? null : 'Certification Lab',
      documents: state === 'not_setup' ? [] : exercises.foundations.documents.map(name => ({ name, document_id: state === 'unavailable' ? null : 'sample', state })) } })
  }
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function openLab() {
  await page.goto(review.baseURL + '/certification')
  const panel = page.locator('[data-cert-panel="true"]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  if (!await panel.getByRole('heading', { name: 'Module 1: Foundations', exact: true }).count()) {
    await panel.getByRole('button', { name: /^1 Foundations/ }).click()
  }
  return panel.getByRole('region', { name: 'Course sample files', exact: true })
}
async function capture(id, lab) {
  await lab.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.equal(await lab.evaluate(el => el.scrollWidth <= el.clientWidth), true)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    const suffix = native ? 'native' : width
    state = 'not_setup'; failStatus = false; progress.modules = {}
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    let lab = await openLab()
    if (native) await review.setBrowserZoom(2)
    const setup = lab.getByRole('button', { name: 'Set Up Lab', exact: true })
    await setup.waitFor()
    await setup.focus()
    await capture(`lab-not-setup-${suffix}`, lab)
    await page.keyboard.press('Enter')
    await lab.getByText('Preparing sample files…', { exact: true }).waitFor()
    await capture(`lab-preparing-${suffix}`, lab)
    assert.equal(await lab.getByRole('button', { name: 'Check sample status' }).isEnabled(), false)
    releasePreparation()
    await lab.getByText('Sample text is not ready yet', { exact: true }).waitFor()
    assert.equal(await lab.getByRole('button', { name: 'Check sample status' }).evaluate(el => el === document.activeElement), true)
    await capture(`lab-processing-${suffix}`, lab)
    const afterSetup = writes
    lab = await openLab()
    await lab.getByText('Sample text is not ready yet', { exact: true }).waitFor()
    assert.equal(writes, afterSetup)
    for (const [next, title] of [['failed', 'Sample processing failed'], ['unavailable', 'Sample status needs attention'], ['ready', 'Sample text is ready']]) {
      state = next
      const check = lab.getByRole('button', { name: 'Check sample status', exact: true })
      await check.focus(); await page.keyboard.press('Enter')
      await lab.getByText(title, { exact: true }).waitFor()
      assert.equal(await check.evaluate(el => el === document.activeElement), true)
      await capture(`lab-${next}-${suffix}`, lab)
    }
    failStatus = true
    await lab.getByRole('button', { name: 'Check sample status', exact: true }).click()
    await lab.getByRole('alert').waitFor()
    await capture(`lab-status-error-${suffix}`, lab)
    assert.equal(await lab.getByText('Sample text is ready', { exact: true }).count(), 0)
    failStatus = false
    await lab.getByRole('button', { name: 'Check sample status', exact: true }).click()
    await lab.getByText('Sample text is ready', { exact: true }).waitFor()
    assert.equal(writes, afterSetup)
    assert.equal(progress.total_xp, 0)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ writes, reads, reloadPreservesProcessing: true, statusChecksNeverProvision: true, earnedCreditUnchanged: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { if (releasePreparation) releasePreparation(); await review.flush(); await review.browser.close() }
