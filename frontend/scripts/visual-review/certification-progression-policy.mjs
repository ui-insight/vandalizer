import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const root = resolve(process.env.REVIEW_PACKAGE || '../artifacts/visual-review/certification-progression-policy-2026-10-07/package-final')
const report = JSON.parse(await readFile(`${root}/preview-report.json`, 'utf8'))
const course = { ...JSON.parse(await readFile(`${root}/public-course.json`, 'utf8')), enrollment_id: 'a'.repeat(32) }
assert.equal(report.enrollment_available, false)
assert.equal(report.grading_available, false)
assert.equal(course.progression_policy.state, 'design_draft')
assert.ok(!JSON.stringify(course.tiers).includes('certified builder'))
assert.ok(!JSON.stringify(course.tiers).includes('earned your certification'))
const progress = { ...course, id: 'qa-policy', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294',
  evidenceMode: 'Actual assembled draft course and pinned progression policy; synthetic enrollment for rendering only. No grading, course write or publication.' })
const { page, context, state } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
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
    const summary = panel.locator('summary').filter({ hasText: /^How learning and credit work$/ })
    await summary.focus(); await page.keyboard.press('Enter')
    const policy = summary.locator('..')
    await policy.getByText('11 required modules · 33 required outcomes · 1850 total base XP', { exact: true }).waitFor()
    await policy.getByText(/Unpublished draft policy/).waitFor()
    assert.equal(await policy.locator('li').count(), course.progression_policy.rules.length)
    await capture(`policy-top-${native ? 'native' : width}`, summary)
    await capture(`policy-recovery-${native ? 'native' : width}`, policy.locator('li').nth(5))
    await capture(`policy-access-${native ? 'native' : width}`, policy.locator('li').last())
    await summary.focus(); await page.keyboard.press('Enter')
    assert.equal(await policy.getAttribute('open'), null)
    await page.keyboard.press('Escape')
    const content = { enrollment_id: course.enrollment_id, course_version: course.course_version,
      course_title: course.course_title, manifest_sha256: course.manifest_sha256, maximum_stars: 1,
      credit_basis: 'required_outcomes', total_xp: 0, level: 'novice', certified: false,
      modules_completed: 0, modules_total: course.modules.length, next_module_id: course.modules[0].id,
      modules: course.modules.map(module => ({ module_id: module.id, title: module.title, xp: module.xp, completed: false, stars: 0 })),
      progression_policy: course.progression_policy }
    const id = `policy-chat-${width}`
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_progress', tool_call_id: id, args: {} },
      { kind: 'tool_result', tool_name: 'get_certification_progress', tool_call_id: id, content }, { kind: 'text', content: id }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show the certification learning policy.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    await page.getByText(id, { exact: true }).waitFor()
    const chatSummary = page.locator('.cert-chat-card summary').filter({ hasText: /^How learning and credit work$/ }).last()
    await chatSummary.focus(); await page.keyboard.press('Enter')
    const chatPolicy = chatSummary.locator('..')
    assert.deepEqual(await chatPolicy.locator('li').allTextContents(), course.progression_policy.rules)
    await capture(`chat-policy-top-${native ? 'native' : width}`, chatSummary)
    await capture(`chat-policy-recovery-${native ? 'native' : width}`, chatPolicy.locator('li').nth(5))
    await capture(`chat-policy-access-${native ? 'native' : width}`, chatPolicy.locator('li').last())
    await chatSummary.focus(); await page.keyboard.press('Enter')
    assert.equal(await chatPolicy.getAttribute('open'), null)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ actualPinnedPolicy: course.progression_policy.policy_id, requiredOutcomes: 33, creditWrites: 0, reads,
    keyboardDetails: true, identicalChatAndPanelRules: true, publicationAvailable: false, intermediateCertificationClaimsRemoved: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
