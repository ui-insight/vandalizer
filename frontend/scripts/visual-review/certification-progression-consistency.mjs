import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5302',
  evidenceMode: 'Frozen certification build; synthetic empty legacy progress. Browser reads only. Actual legacy and pinned server grading is verified separately in isolated MongoDB.' })
const { page, context } = review
const exercises = JSON.parse(await readFile('../backend/certification-data/exercises.json', 'utf8'))
const requests = []
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); requests.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: { id: 'legacy-order', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, unlocked: false } })
  if (path.endsWith('/modules/governance/exercise')) return route.fulfill({ json: exercises.governance })
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
  for (const width of native ? [780] : [320, 1440]) {
    const suffix = native ? 'native' : width
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const module = panel.getByRole('button', { name: /Collaboration & Governance/ })
    await module.waitFor()
    assert.equal(await module.isEnabled(), true)
    assert.equal(await panel.getByRole('button', { name: /Thinking in Workflows/ }).isEnabled(), true)
    await module.scrollIntoViewIfNeeded()
    await capture(`legacy-any-order-${suffix}`)
    await module.focus(); await page.keyboard.press('Enter')
    await panel.getByRole('heading', { name: 'Module 10: Collaboration & Governance', exact: true }).waitFor()
    await panel.getByText(/Your VWA credential requires completion of every course module\./).waitFor()
    await capture(`legacy-later-module-${suffix}`)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ emptyLegacyProgress: true, originalUnlockFlag: false, laterModuleKeyboardEntry: true, requests, creditWrites: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
