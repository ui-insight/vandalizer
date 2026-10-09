import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const { password } = JSON.parse(await readFile('/private/tmp/vandalizer-ra8-backend/runtime.json', 'utf8'))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5181', isolatedBackend: true, resetStorage: false })
const { page, context } = review
page.setDefaultTimeout(20000)
async function shot(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [])
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  console.log('Captured ' + id)
}
try {
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: width === 320 ? 660 : 1000 })
    await page.goto(review.baseURL)
    await page.getByRole('button', { name: 'Sign in', exact: true }).first().waitFor()
    await shot('live-public-entry-' + width)
    await page.getByRole('button', { name: 'Sign in', exact: true }).first().click()
    await page.getByRole('textbox', { name: 'Email', exact: true }).waitFor()
    await shot('live-public-sign-in-' + width)
  }
  const login = await context.request.post(review.baseURL + '/api/auth/login', { data: { user_id: 'ra8-member@example.test', password } })
  assert.ok(login.ok())
  await page.setViewportSize({ width: 320, height: 660 })
  await page.goto(review.baseURL + '/certification')
  const position = page.getByRole('combobox', { name: 'Learning panel position', exact: true })
  await position.selectOption('fullscreen')
  await page.getByRole('button', { name: /^0 AI Literacy/ }).click()
  await page.getByRole('button', { name: /^Lesson 1:/ }).click()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByText('Lesson 2 of 9', { exact: true }).waitFor()
  await shot('live-learning-lesson-progress-320')
  await page.getByRole('button', { name: 'Return to workspace', exact: true }).click()
  await page.goto(review.baseURL + '/certification')
  await position.selectOption('fullscreen')
  // The open module may itself be restored; otherwise select it again.
  if (await page.getByRole('button', { name: /^0 AI Literacy/ }).count()) await page.getByRole('button', { name: /^0 AI Literacy/ }).click()
  await page.getByText('Lesson 2 of 9', { exact: true }).waitFor()
  await shot('live-learning-resumed-320')
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const submit = page.getByRole('button', { name: 'Submit Self-Assessment', exact: true })
  if (await submit.count()) {
    assert.equal(await submit.isDisabled(), true)
    for (const name of ['experience', 'comfort', 'concern']) await page.locator('input[type=radio][name="' + name + '"]').first().check()
    await submit.click()
  }
  await page.getByRole('heading', { name: 'Reflection answers saved', exact: true }).waitFor()
  await shot('live-learning-assessment-saved-320')
  const complete = page.getByRole('button', { name: 'Complete Module', exact: true })
  if (await complete.count()) await complete.click()
  const celebration = page.getByRole('dialog', { name: 'Module complete', exact: true })
  await celebration.waitFor()
  for (let i = 0; i < 3; i++) { await page.keyboard.press('Tab'); assert.ok(await celebration.evaluate(e => e.contains(document.activeElement))) }
  await shot('live-learning-module-completion-320')
  await page.keyboard.press('Escape')
  await celebration.waitFor({ state: 'hidden' })
  await page.getByRole('dialog', { name: 'Learning and certification', exact: true }).waitFor()
  const progressResponse = await context.request.get(review.baseURL + '/api/certification/progress')
  const progress = await progressResponse.json()
  assert.equal(progress.modules.ai_literacy.completed, true)
  assert.equal(progress.modules.foundations?.completed ?? false, false)
  assert.equal(progress.certified, false)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('button', { name: /^1 Foundations/ }).waitFor()
  assert.equal(await page.getByRole('button', { name: /^1 Foundations/ }).isDisabled(), false)
  await shot('live-learning-foundations-unlocked-1440')
  assert.deepEqual(review.errors, [])
  review.observations.push('Actual local first-module lesson resumption, saved reflective assessment, completion and next-module unlock. Course completion and model-backed lab modules remain unverified. Public entry/sign-in captured without a session. No intercepted API data.')
} catch (error) { await review.capture('isolated-learning-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
