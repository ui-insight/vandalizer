import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const lessons = JSON.parse(await readFile('../backend/certification-data/lessons.json', 'utf8'))
const exercises = JSON.parse(await readFile('../backend/certification-data/exercises.json', 'utf8'))
const definition = lessons.ai_literacy.assessment
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5304', resetStorage: false,
  evidenceMode: 'Frozen frontend and actual authored reflection definition. Synthetic save failure/success; all course writes intercepted. Browser-tab draft restoration and separate server-save presentation.' })
const { page, context } = review
const progress = { id: 'reflection-draft', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, unlocked: false }
let failSave = true
let failStatus = 503
let expiredRefreshes = 0
let blockedSave = null
const submissions = []
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await context.route('**/api/auth/refresh', route => { expiredRefreshes++; return route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }) })
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/modules/ai_literacy/assessment')) {
    assert.equal(request.method(), 'POST')
    const body = request.postDataJSON(); submissions.push(body)
    const expected = Object.fromEntries(definition.questions.map(question => [question.key, question.options[1]]))
    assert.deepEqual(body.answers, expected)
    if (blockedSave) await blockedSave
    if (failSave) return route.fulfill({ status: failStatus, json: { detail: failStatus === 401 ? 'Not authenticated' : 'Synthetic save unavailable' } })
    progress.modules.ai_literacy = { completed: false, stars: 0, xp_earned: 0, attempts: 0, self_assessment: body.answers }
    return route.fulfill({ json: { stored: true, module_id: 'ai_literacy' } })
  }
  assert.equal(request.method(), 'GET')
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/modules/ai_literacy/exercise')) return route.fulfill({ json: exercises.ai_literacy })
  return route.fallback()
})
async function openReflection() {
  await page.goto(review.baseURL + '/certification')
  const panel = page.locator('[data-cert-panel="true"]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  if (!await panel.getByRole('button', { name: 'Challenge', exact: true }).count()) await panel.getByRole('button', { name: 'Continue: AI Literacy', exact: true }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  return panel
}
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    const suffix = native ? 'native' : width
    progress.modules = {}; failSave = true; failStatus = 503
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL)
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
    let panel = await openReflection()
    if (native) await review.setBrowserZoom(2)
    const questions = panel.getByRole('radiogroup')
    await questions.first().getByRole('radio').nth(1).check()
    await capture(`reflection-draft-${suffix}`, panel.getByText(/Draft saved in this browser tab/))
    panel = await openReflection()
    assert.equal(await panel.getByRole('radio', { checked: true }).count(), 1)
    for (const group of await panel.getByRole('radiogroup').all()) await group.getByRole('radio').nth(1).check()
    const before = submissions.length
    if (process.env.REVIEW_PENDING_ACTIONS === '1') {
      let releaseSave
      blockedSave = new Promise(resolve => { releaseSave = resolve })
      const sent = page.waitForRequest('**/modules/ai_literacy/assessment')
      await panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).evaluate(button => { button.click(); button.click() })
      await sent
      const saving = panel.getByRole('button', { name: 'Saving...', exact: true })
      await saving.waitFor()
      assert.equal(await saving.isDisabled(), true)
      assert.equal(submissions.length, before + 1)
      await capture(`reflection-pending-once-${suffix}`, saving)
      blockedSave = null
      releaseSave()
    } else await panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).click()
    await page.getByText('Could not submit your answers right now. Please try again.', { exact: true }).waitFor()
    assert.equal(submissions.length, before + 1)
    panel = await openReflection()
    assert.equal(await panel.getByRole('radio', { checked: true }).count(), definition.questions.length)
    await capture(`reflection-restored-after-error-${suffix}`, panel.getByText(/Draft saved in this browser tab/))
    failStatus = 401
    await panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).click()
    await page.getByText('Could not submit your answers right now. Please try again.', { exact: true }).waitFor()
    assert.equal(submissions.length, before + 2)
    panel = await openReflection()
    assert.equal(await panel.getByRole('radio', { checked: true }).count(), definition.questions.length)
    await capture(`reflection-restored-after-expiry-${suffix}`, panel.getByText(/Draft saved in this browser tab/))
    failSave = false
    await panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).click()
    await panel.getByText('Reflection answers saved', { exact: true }).waitFor()
    assert.equal(submissions.length, before + 3)
    assert.deepEqual(submissions.at(-1), submissions.at(-2))
    assert.equal(await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('cert-reflection-draft:')).length), 0)
    await capture(`reflection-server-saved-${suffix}`, panel.getByText('Reflection answers saved', { exact: true }))
    progress.modules = {}
    panel = await openReflection()
    await page.evaluate(() => {
      window.reflectionOriginalSetItem = Storage.prototype.setItem
      Storage.prototype.setItem = function(key, value) { if (key.startsWith('cert-reflection-draft:')) throw new Error('Synthetic storage failure'); return window.reflectionOriginalSetItem.call(this, key, value) }
    })
    await panel.getByRole('radio').first().check()
    await capture(`reflection-storage-unavailable-${suffix}`, panel.getByText(/This browser could not save your draft/))
    await page.evaluate(() => { Storage.prototype.setItem = window.reflectionOriginalSetItem; delete window.reflectionOriginalSetItem })
    assert.equal(progress.total_xp, 0); assert.equal(progress.certified, false)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  assert.equal(expiredRefreshes, native ? 1 : 2)
  review.observations.push({ draftsSurviveReload: true, failedSavePreservesChoices: true, expiredSessionPreservesChoices: true, expiredRefreshes, identicalExplicitRetry: true, serverSaveClearsDraft: true, storageFailureExplained: true, allWritesIntercepted: true, interceptedSubmissions: submissions.length })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
