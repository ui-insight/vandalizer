import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
let metadataFails = true, acceptFails = true, accepts = 0
await page.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await page.route('**/api/teams/invite/info/*', route => route.fulfill(metadataFails
  ? { status: 503, json: { detail: 'Temporarily unavailable' } }
  : { json: { email: 'reviewer@example.test', role: 'member', team_name: 'Research administration', inviter_name: 'QA owner', expired: false } }))
await page.route('**/api/teams/invite/accept/*', async route => {
  accepts++
  await new Promise(resolve => setTimeout(resolve, 300))
  await route.fulfill(acceptFails ? { status: 503, json: { detail: 'Joining failed. Retry this invitation.' } } : { json: { uuid: 'team-1', name: 'Research administration' } })
})
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [])
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
}
try {
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: width === 320 ? 660 : 1000 })
    metadataFails = true; acceptFails = true; accepts = 0
    await page.goto(review.baseURL + '/invite?token=qa-invitation')
    await page.getByRole('button', { name: 'Retry invitation' }).waitFor()
    await capture('invitation-read-retry-' + width)
    metadataFails = false
    await page.getByRole('button', { name: 'Retry invitation' }).click()
    await page.getByRole('alert').filter({ hasText: 'Joining failed' }).waitFor()
    assert.equal(accepts, 1)
    await capture('invitation-accept-retry-' + width)
    acceptFails = false
    await page.getByRole('button', { name: 'Retry invitation' }).click()
    await page.getByRole('heading', { name: "You've joined Research administration!" }).waitFor()
    assert.equal(accepts, 2)
    await capture('invitation-accepted-' + width)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push('Synthetic invitation metadata and acceptance failure/retry at 320/1440; one acceptance per attempt. Actual invitation identity/role enforcement is covered separately by isolated collaboration API evidence.')
} finally { await review.flush(); await review.browser.close() }
