import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const all = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const modules = all.filter(m => ['ai_literacy', 'process_mapping', 'foundations', 'extraction_engine'].includes(m.id))
const identity = { enrollment_id: 'qa-three-module-completion', course_version: 'qa-completion', manifest_sha256: 'd'.repeat(64), course_title: 'Supervision bridge — preserved course completion', modules_total: 4, module_ids: modules.map(m => m.id), maximum_xp: 500 }
const course = { ...structure, ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])) }
course.tiers = [{ ...structure.tiers.at(-1), moduleIds: ['ai_literacy', 'process_mapping', 'foundations'] }]
const progress = { ...identity, id: 'qa-completion', user_id: 'reviewer', modules: { ai_literacy: { completed: true, stars: 2, xp_earned: 100 }, process_mapping: { completed: true, stars: 2, xp_earned: 100 }, foundations: { provisioned_docs: ['synthetic-document'] } }, total_xp: 200, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend with preserved certification-claim tier copy, all tier modules complete but one course module outstanding. Synthetic completion only; no actual credit or credential.' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (req.method() === 'POST' && path.endsWith('/complete')) {
    writes.push(path)
    progress.certified = false; progress.total_xp = 300
    progress.modules.foundations = { completed: true, stars: 2, xp_earned: 100, provisioned_docs: ['synthetic-document'] }
    return route.fulfill({ json: { ...identity, module_id: 'foundations', stars: 2, xp_earned: 100, total_xp: 300, level: 'novice', level_up: false, certified: false, validation: { passed: true, stars: 2, checks: [] } } })
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
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByText('Course progress and credential', { exact: true }).click()
  const moduleProgress = page.getByRole('progressbar', { name: 'Course modules completed', exact: true })
  assert.equal(await moduleProgress.getAttribute('aria-valuenow'), '50')
  await moduleProgress.scrollIntoViewIfNeeded()
  await capture('module-progress-before-completion')
  await page.getByRole('button', { name: /^1 Foundations/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await page.getByRole('button', { name: 'Complete Module', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Module complete', exact: true })
  await dialog.getByText('You have completed the modules in this tier. Continue with the remaining course requirements to earn your certification.', { exact: true }).waitFor()
  assert.equal(await dialog.getByText(course.tiers[0].celebration, { exact: true }).count(), 0)
  assert.equal(await dialog.getByRole('button', { name: 'View Certificate', exact: true }).count(), 0)
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1000 : 500 })
    if (native) await review.setBrowserZoom(2)
    const view = dialog.getByRole('button', { name: 'Continue', exact: true })
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
  await page.keyboard.press('Enter')
  await dialog.waitFor({ state: 'hidden' })
  assert.equal(await page.locator('[data-cert-certificate]').count(), 0)
  assert.equal(writes.length, 1)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ completedModules: 3, totalModules: 4, tierCompleted: true, certified: false, preservedTierMessageSuppressed: course.tiers[0].celebration, completionWrites: 1, modalTabContainment: true, realCreditOrCredential: false })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
