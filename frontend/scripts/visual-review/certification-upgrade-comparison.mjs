import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const outcomes = await read('drafts/v5.0/outcomes.json')
const identity = { enrollment_id: 'comparison-source', course_version: 'continuation-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Your existing certification course', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, id: 'comparison-progress', user_id: 'reviewer', modules: { foundations: { completed: true, stars: 1, xp_earned: 125, completed_at: '2025-01-01', attempts: 1 } }, total_xp: 125, level: 'novice', certified: false, certified_at: null, last_activity_date: null, learning_position: null }
const target = { course_version: 'v5-comparison-fixture', course_title: 'Vandalizer 5.0 — Supervise document work', description: 'Compare source review, scope, recovery and delivery requirements before deciding on a future optional upgrade.', manifest_sha256: 'b'.repeat(64), required_outcome_count: 33 }
const preview = { policy: 'optional', can_activate: false, preview_sha256: 'c'.repeat(64), source: { ...identity, provenance: 'legacy_version_unknown', total_xp: 125, certified: false, credential_preserved: false, completed_modules: [{ module_id: 'foundations', title: 'Foundations', xp_earned: 125, stars: 1, completed_at: '2025-01-01' }], has_saved_place: true }, target: { ...target, transferred_outcome_count: 0, modules: outcomes.modules.map(module => ({ module_id: module.module_id, title: modules.find(m => m.id === module.module_id).title, outcomes: module.outcomes.map(outcome => ({ outcome_id: outcome.id, statement: outcome.statement, disposition: 'requires_assessment', reason: 'No confirmed outcome equivalence.' })) })) }, saved_work: [{ kind: 'prepared_labs', label: 'Saved lab inputs', count: 1 }, { kind: 'saved_lab_runs', label: 'Saved lab runs', count: 2 }, { kind: 'saved_learner_decisions', label: 'Saved learner decisions', count: 3 }], work_in_flight: true, unfinished_answers: true, credential_needs_preservation: false }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292' })
const { page, context } = review
const writes = [], requests = []
let mode = 'offered'
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/upgrade-options')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    requests.push('options')
    return route.fulfill({ json: { enrollment_id: identity.enrollment_id, policy: 'optional', can_activate: false, courses: mode === 'empty' ? [] : [target] } })
  }
  if (path.endsWith('/upgrade-preview')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    assert.equal(url.searchParams.get('target_version'), target.course_version)
    requests.push('preview')
    if (mode === 'error' || mode === 'conflict') return route.fulfill({ status: mode === 'error' ? 503 : 409, json: { detail: 'Synthetic comparison recovery case' } })
    return route.fulfill({ json: preview })
  }
  return route.fallback()
})
async function capture(id) {
  assert.equal(await page.getByText(/-\d+ XP to/).count(), 0)
  await review.capture(id, 'Actual production frontend with synthetic published-offer and preserved-work fixtures. GET-only comparison; no enrollment, credit, model or live migration changes.')
  if (process.env.REVIEW_TEXT_SCALE === '2' && !id.includes('highest-xp') && id !== 'blocked') {
    const overflow = await page.getByRole('region', { name: 'Course versions are your choice', exact: true }).evaluate(root =>
      [root, ...root.querySelectorAll('button,p,h3,h4,h5,summary,li')].filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1)
        .map(el => ({ tag: el.tagName, text: el.textContent.slice(0, 100), width: el.clientWidth, content: el.scrollWidth })))
    assert.deepEqual(overflow, [], 'Course comparison content overflows its container at enlarged text')
  }
  console.log(id)
}
try {
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByText('Course progress and credential', { exact: true }).click()
  const section = page.getByRole('region', { name: 'Course versions are your choice', exact: true })
  await section.getByRole('button', { name: 'Compare course versions', exact: true }).waitFor()
  assert.deepEqual(requests, [])
  if (process.env.REVIEW_XP_ONLY !== '1') {
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await section.getByRole('heading', { name: 'Course versions are your choice', exact: true }).scrollIntoViewIfNeeded()
    await capture('comparison-entry-' + width)
    await section.getByRole('button', { name: 'Compare course versions', exact: true }).click()
    const compare = section.getByRole('button', { name: `Compare ${target.course_title}`, exact: true })
    await compare.scrollIntoViewIfNeeded()
    await capture('comparison-offer-' + width)
    await compare.click()
    const current = section.getByRole('heading', { name: 'Your course comparison', exact: true })
    await current.scrollIntoViewIfNeeded()
    await capture('comparison-preserved-credit-' + width)
    const requirements = section.getByText('Foundations — 3 outcomes to assess', { exact: true })
    await requirements.click()
    await requirements.scrollIntoViewIfNeeded()
    await capture('comparison-requirements-' + width)
    await section.getByRole('heading', { name: 'Work that stays in this course', exact: true }).scrollIntoViewIfNeeded()
    await capture('comparison-saved-work-' + width)
    assert.equal(await section.getByRole('button', { name: /Activate|Switch|Start new course/ }).count(), 0)
    await section.getByRole('button', { name: 'Close comparison', exact: true }).click()
    await page.waitForFunction(() => document.activeElement?.textContent === 'Compare course versions')
    assert.equal(progress.total_xp, 125)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const state of ['error', 'conflict']) {
    mode = state
    await section.getByRole('button', { name: 'Compare course versions', exact: true }).click()
    await section.getByRole('button', { name: `Compare ${target.course_title}`, exact: true }).click()
    await section.getByRole('alert').scrollIntoViewIfNeeded()
    await capture('comparison-' + state + '-390')
    if (state === 'conflict') await section.getByRole('button', { name: 'Refresh my course', exact: true }).click()
    else await section.getByRole('button', { name: 'Close course options', exact: true }).click()
  }
  mode = 'empty'
  await section.getByRole('button', { name: 'Compare course versions', exact: true }).click()
  await section.getByText(/No other course version is currently offered/).scrollIntoViewIfNeeded()
  await capture('comparison-no-offer-390')
  assert.equal(await page.getByText('125 XP to Builder', { exact: true }).count(), 1)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  progress.total_xp = 1800
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByText('Course progress and credential', { exact: true }).click()
  assert.equal(await page.getByText('Highest XP threshold reached', { exact: true }).isVisible(), true)
  await page.getByText('1800 XP', { exact: true }).waitFor({ state: 'visible' })
  await page.getByText('Highest XP threshold reached', { exact: true }).scrollIntoViewIfNeeded()
  await capture('comparison-highest-xp-390')
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  for (const capture of review.captures) {
    assert.equal(capture.pageWidth, capture.viewport.width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [], `Accessibility violations: ${capture.id}`)
  }
  review.observations.push({ publishedOfferOnly: true, widths: [...new Set(review.captures.map(item => item.viewport.width))], reads: requests.length, writes, originalXp: 125, highestXpFixture: progress.total_xp, activated: false })
} catch (error) {
  console.error('Comparison check failed:', error)
  try { await capture('blocked') } catch (captureError) { console.error('Failure capture unavailable:', captureError) }
  throw error
} finally { await review.flush(); await review.browser.close() }
