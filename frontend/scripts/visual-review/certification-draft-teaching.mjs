import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

// Synthetic delivery of an unpublished teaching draft, with no lab or credit writes.
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const moduleId = process.env.REVIEW_MODULE || 'foundations'
assert.match(moduleId, /^[a-z_]+$/)
const draft = await read(`drafts/v5.0/${moduleId.replaceAll('_', '-')}-teaching.json`)
const modules = await read('panel-modules.json')
const module = modules.find(item => item.id === moduleId)
assert.ok(module)
assert.deepEqual(draft.replacements.map(lesson => lesson.id), module.lessons.map(lesson => lesson.id))
const workingTeaching = process.env.REVIEW_WORKING_TEACHING === '1'
if (!workingTeaching) {
  module.lessons = draft.replacements.map(lesson => ({ ...lesson, knowledgeCheck: lesson.knowledge_check }))
  Object.assign(module, draft.module_patch)
}
const selectedIds = new Set((process.env.REVIEW_LESSONS || '').split(',').filter(Boolean))
assert.ok([...selectedIds].every(id => module.lessons.some(lesson => lesson.id === id)), 'Requested lesson must belong to this module')
const selectedLessons = module.lessons.filter(lesson => selectedIds.size === 0 || selectedIds.has(lesson.id))
const captureTexts = JSON.parse(process.env.REVIEW_CAPTURE_TEXTS || '[]')
assert.ok(Array.isArray(captureTexts) && captureTexts.every(value => typeof value === 'string' && value.length))
const capturedTexts = new Set()
const structure = await read('course-structure.json')
const identity = { enrollment_id: `qa-v5-teaching-${moduleId}`, course_version: 'qa-v5-teaching-draft', manifest_sha256: 'd'.repeat(64), course_title: 'V5 teaching — local QA fixture', modules_total: modules.length, module_ids: modules.map(item => item.id), maximum_xp: 2675 }
const progress = { ...identity, id: 'qa-draft-teaching', user_id: 'reviewer', modules: {}, learning_position: null, position_revision: 0, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5292' })
const { page, context } = review
const nativeZoom = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const widths = (process.env.REVIEW_WIDTHS || (nativeZoom ? '640,1440' : '320,390,1440')).split(',').map(Number)
assert.ok(widths.every(width => Number.isInteger(width) && width >= 320 && width <= 2880))
const practiceWidth = widths.includes(390) ? 390 : widths[0]
const writes = []
if (process.env.REVIEW_ACCENT) await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: process.env.REVIEW_ACCENT, ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/position') && request.method() === 'PUT') {
    const body = request.postDataJSON()
    assert.equal(body.module_id, moduleId)
    assert.ok(module.lessons.some(lesson => lesson.id === body.lesson_id))
    const selected = module.lessons.find(lesson => lesson.id === body.lesson_id)
    progress.learning_position = { module_id: moduleId, lesson_id: body.lesson_id, revision: selected.revision, content_sha256: 'e'.repeat(64), saved_at: new Date().toISOString() }
    progress.position_revision++
    progress.modules[moduleId] = { learning_position: progress.learning_position }
    return route.fulfill({ json: { saved: true, enrollment_id: identity.enrollment_id, course_version: identity.course_version, learning_position: progress.learning_position, position_revision: progress.position_revision } })
  }
  if (request.method() !== 'GET') writes.push(path)
  return route.fallback()
})
async function capture(id) {
  await review.capture(id, `${workingTeaching ? 'Current working teaching' : 'Unpublished teaching draft'} in actual production frontend. Synthetic position persistence; no lab, model execution or graded assessment tested.`)
  console.log(id)
}
try {
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  for (const width of widths) {
    await page.setViewportSize({ width, height: nativeZoom ? 1000 : width < 500 ? 844 : 1000 })
    if (nativeZoom) await review.setBrowserZoom(2)
    const readingWidth = await page.evaluate(() => innerWidth)
    for (const [index, lesson] of module.lessons.entries()) {
      if (selectedIds.size && !selectedIds.has(lesson.id)) continue
      await page.getByRole('button', { name: new RegExp(`^Lesson ${index + 1}:`) }).click()
      await page.getByText('Place saved across devices.', { exact: true }).waitFor()
      if (workingTeaching) {
        const closedGlossary = page.locator('[data-cert-panel] details:not([open]) > summary')
        const closedCount = await closedGlossary.count()
        for (let index = 0; index < closedCount; index++) await closedGlossary.first().click()
      }
      const heading = page.getByRole('heading', { name: lesson.title, exact: true })
      await heading.evaluate(element => element.scrollIntoView({ block: 'start' }))
      const navigation = page.getByRole('navigation', { name: 'Lessons in this module', exact: true })
      assert.equal(await navigation.evaluate(element => element.scrollWidth <= element.clientWidth), true)
      assert.equal(await page.locator('[data-cert-panel]').evaluate(element => [...element.querySelectorAll('*')].every(child => child.scrollLeft === 0)), true)
      const bounds = await heading.boundingBox()
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= readingWidth)
      const breadcrumb = page.getByText(`Module ${module.number}: ${module.title}`, { exact: true }).and(page.locator('span'))
      assert.equal(await breadcrumb.evaluate(element => element.scrollWidth <= element.clientWidth), true, 'The module breadcrumb must wrap without truncation')
      await capture(`${moduleId}-${index + 1}-reading-${width}`)
      if (process.env.REVIEW_CAPTURE_TEXT) {
        const detail = page.locator('[data-cert-panel] p').filter({ hasText: process.env.REVIEW_CAPTURE_TEXT })
        const count = await detail.count()
        assert.ok(count <= 1, 'The requested teaching detail must identify one paragraph')
        if (count) { await detail.scrollIntoViewIfNeeded(); await capture(`${moduleId}-${index + 1}-detail-${width}`) }
      }
      for (const [detailIndex, text] of captureTexts.entries()) {
        const detail = page.locator('[data-cert-panel] p, [data-cert-panel] li:not(:has(p))').filter({ hasText: text })
        const count = await detail.count()
        assert.ok(count <= 1, 'The requested teaching detail must identify one paragraph or step')
        if (count) {
          await detail.scrollIntoViewIfNeeded()
          await capture(`${moduleId}-${index + 1}-detail-${detailIndex + 1}-${width}`)
          capturedTexts.add(text)
        }
      }
      if (!lesson.knowledgeCheck) continue
      await page.getByText(lesson.knowledgeCheck.question, { exact: true }).scrollIntoViewIfNeeded()
      await capture(`${moduleId}-${index + 1}-practice-${width}`)
      if (width === practiceWidth) {
        const wrong = lesson.knowledgeCheck.options.find(option => !option.correct)
        const correct = lesson.knowledgeCheck.options.find(option => option.correct)
        await page.getByRole('radio', { name: wrong.text, exact: true }).check()
        await page.getByRole('button', { name: 'Check answer', exact: true }).click()
        await page.getByText(wrong.explanation, { exact: false }).waitFor()
        await page.getByRole('radio', { name: correct.text, exact: true }).check()
        await page.getByRole('button', { name: 'Check answer', exact: true }).click()
        await page.getByText(correct.explanation, { exact: false }).scrollIntoViewIfNeeded()
        await capture(`${moduleId}-${index + 1}-feedback-${width}`)
      }
    }
  }
  assert.deepEqual(writes, [])
  assert.equal(capturedTexts.size, captureTexts.length, 'Every requested teaching detail must be inspected')
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
  for (const capture of review.captures) {
    assert.equal(capture.pageWidth, capture.viewport.width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [], `Accessibility violations: ${capture.id}`)
  }
  review.observations.push({ moduleId, workingTeaching, lessons: selectedLessons.map(lesson => ({ id: lesson.id, revision: lesson.revision })), physicalWidths: widths, nativeZoom: nativeZoom ? 2 : 1, practiceCorrections: selectedLessons.filter(lesson => lesson.knowledgeCheck).length, unexpectedWrites: writes, creditAwarded: 0 })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
