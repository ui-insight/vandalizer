import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const root = resolve('../artifacts/visual-review/certification-credential-scope-2026-10-08')
const course = { ...JSON.parse(await readFile(`${root}/package/public-course.json`, 'utf8')), enrollment_id: 'qa-scope-selected' }
const original = JSON.parse(await readFile(`${root}/certificate-normal.json`, 'utf8')).credential_summary
assert.equal(course.credential_scope.state, 'design_draft')
assert.equal(course.credential_scope.promise, original.credential_scope.promise)
const progress = { ...course, id: 'qa-scope', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Assembled draft course and actual synthetic full-course credential API summary. Rendering uses intercepted GET responses; no learner writes or live grading. Original issuance was verified separately on disposable MongoDB with stubbed providers.' })
const { page, context } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [original] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: course.enrollment_id, pending: null } })
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
  if (native) assert.equal(shot.viewport.width, 390)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 390, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByLabel('Your course', { exact: true }).waitFor()
    await panel.getByText('Course progress and credential', { exact: true }).click()
    for (const [label, title, scope] of [['course', 'Course goal and certificate scope', course.credential_scope],
      ['credential', 'Recorded certificate scope', original.credential_scope]]) {
      const summary = panel.locator('summary').filter({ hasText: new RegExp(`^${title}$`) })
      await summary.focus(); await page.keyboard.press('Enter')
      const details = summary.locator('..')
      await details.getByText(scope.promise, { exact: true }).waitFor()
      await details.getByText(scope.agent_assistance, { exact: false }).waitFor()
      for (const exclusion of scope.exclusions) await details.getByText(exclusion, { exact: true }).waitFor()
      assert.equal(await details.getByText(/Unpublished course goal/).count(), label === 'course' ? 1 : 0)
      await capture(`${label}-promise-${width}`, summary)
      await capture(`${label}-limits-${width}`, details.locator('li').last())
      await summary.focus(); await page.keyboard.press('Enter')
      assert.equal(await details.getAttribute('open'), null)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ originalCredentialId: original.credential_id, originalScope: original.credential_scope,
    currentManifest: course.manifest_sha256, currentCourseIsDraft: true, credentialScopeIsRecorded: true,
    certificationWrites: 0, reads, liveModelVerified: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
