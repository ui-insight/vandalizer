import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const all = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const modules = all.filter(m => ['ai_literacy', 'process_mapping', 'foundations'].includes(m.id))
const identity = { enrollment_id: 'qa-three-module-completion', course_version: 'qa-completion', manifest_sha256: 'd'.repeat(64), course_title: 'Supervision bridge — preserved course completion', modules_total: 3, module_ids: modules.map(m => m.id), maximum_xp: 300 }
const course = { ...structure, ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])) }
const progress = { ...identity, id: 'qa-completion', user_id: 'reviewer', modules: { ai_literacy: { completed: true, stars: 2, xp_earned: 100 }, process_mapping: { completed: true, stars: 2, xp_earned: 100 }, foundations: { provisioned_docs: ['synthetic-document'] } }, total_xp: 200, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend with a synthetic three-module completion response; no real course, credit, migration or issued credential.' })
const { page, context } = review
const touch = process.env.REVIEW_TOUCH === '1'
const activate = locator => touch ? locator.tap() : locator.click()
const writes = []
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (req.method() === 'POST' && path.endsWith('/complete')) {
    writes.push(path)
    progress.certified = true; progress.total_xp = 300
    progress.modules.foundations = { completed: true, stars: 2, xp_earned: 100, provisioned_docs: ['synthetic-document'] }
    return route.fulfill({ json: { ...identity, module_id: 'foundations', stars: 2, xp_earned: 100, total_xp: 300, level: 'novice', level_up: false, certified: true, validation: { passed: true, stars: 2, checks: [] } } })
  }
  assert.equal(req.method(), 'GET', `Unexpected write ${path}`)
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
// macOS WebKit's default Tab skips buttons; Option+Tab includes all controls.
// Use the engine's actual keyboard navigation, without changing the user's settings.
const tabKey = process.env.REVIEW_ENGINE === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab'
async function capture(id) {
  await review.capture(id)
  const c = review.captures.at(-1)
  assert.equal(c.pageWidth, c.viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
try {
  if (touch) await page.setViewportSize({ width: 320, height: 500 })
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await activate(page.getByText('Course progress and credential', { exact: true }))
  const moduleProgress = page.getByRole('progressbar', { name: 'Course modules completed', exact: true })
  assert.equal(await moduleProgress.getAttribute('aria-valuenow'), '67')
  await moduleProgress.scrollIntoViewIfNeeded()
  await capture('module-progress-before-completion')
  await activate(page.getByRole('button', { name: /^1 Foundations/ }))
  await activate(page.getByRole('button', { name: 'Challenge', exact: true }))
  await activate(page.getByRole('button', { name: 'Complete Module', exact: true }))
  const dialog = page.getByRole('dialog', { name: 'Course complete', exact: true })
  await dialog.getByText('You have completed all 3 modules in this course.', { exact: true }).waitFor()
  assert.equal(await dialog.getByRole('heading', { name: identity.course_title, exact: true }).count(), 1)
  assert.equal(await dialog.getByText(`Course version: ${identity.course_version}`, { exact: true }).count(), 1)
  assert.equal(await dialog.getByRole('img', { name: '2 of 3 stars', exact: true }).count(), 1)
  for (const width of native ? [640, 780, 1440] : touch ? [320] : [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: native ? 1000 : 500 })
    if (native) await review.setBrowserZoom(2)
    const view = dialog.getByRole('button', { name: 'View Certificate', exact: true })
    await view.focus()
    assert.equal(await view.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth }), true)
    await page.keyboard.press(tabKey)
    const details = dialog.getByRole('region', { name: 'Completion details', exact: true })
    assert.equal(await details.evaluate(el => document.activeElement === el), true, 'Tab wraps within the modal to its scrollable content')
    await page.keyboard.press('End')
    await page.keyboard.press(tabKey)
    assert.equal(await view.evaluate(el => document.activeElement === el), true, 'Tab returns to the reachable modal action')
    const moving = await dialog.evaluate(el => [...el.querySelectorAll('*')].filter(e => { const s = getComputedStyle(e); return s.animationName !== 'none' || s.transitionDuration.split(',').some(v => parseFloat(v) > 0) }).length)
    assert.equal(moving, 0)
    await capture(`completion-focus-${native ? 'native200' : 'short'}-${width}`)
  }
  if (touch) await activate(dialog.getByRole('button', { name: 'View Certificate', exact: true })); else await page.keyboard.press('Enter')
  await dialog.waitFor({ state: 'hidden' })
  const download = page.locator('[data-cert-certificate]').getByRole('button', { name: 'Download certificate (PDF)', exact: true })
  await download.waitFor()
  assert.equal(await page.locator('[data-cert-certificate]').getByText(`Course version: ${identity.course_version}`, { exact: true }).count(), 1)
  assert.equal(await download.evaluate(el => document.activeElement === el), true)
  await capture('certificate-focus-restored')
  await page.keyboard.press('Escape')
  await page.locator('[data-cert-panel]').waitFor({ state: 'hidden' })
  assert.equal(writes.length, 1)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ actualCompletedCourseModules: 3, completionWrites: 1, touchEmulation: touch, certificateActionReachedByKeyboard: true, navigationKey: tabKey, modalTabContainment: true, reducedMotion: true, realCreditOrCredential: false })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
