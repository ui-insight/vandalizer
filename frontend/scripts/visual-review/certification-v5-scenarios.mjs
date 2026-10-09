import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const moduleId = process.env.REVIEW_MODULE || 'ai_literacy'
assert.match(moduleId, /^[a-z_]+$/)
const module = modules.find(item => item.id === moduleId)
assert.ok(module)
const teaching = await read(`drafts/v5.0/${moduleId.replaceAll('_', '-')}-teaching.json`)
const bank = await read(`drafts/v5.0/${moduleId.replaceAll('_', '-')}-scenarios.json`)
const definition = { bank_id: bank.bank_id, revision: bank.revision, bank_sha256: 'a'.repeat(64), module_id: bank.module_id,
  questions: bank.questions.map(q => ({ id: q.id, prompt: q.prompt, choices: q.choices.map(c => ({ id: c.id, text: c.text })) })) }
for (const replacement of teaching.replacements) {
  const index = module.lessons.findIndex(lesson => lesson.id === replacement.id)
  assert.ok(index >= 0)
  module.lessons[index] = { ...replacement, knowledgeCheck: replacement.knowledge_check }
}
Object.assign(module, teaching.module_patch ?? {})
module.scenarioAssessment = definition
module.assessment = null
const identity = { enrollment_id: 'qa-v5-scenario-enrollment', course_version: 'qa-v5-scenario-draft', manifest_sha256: 'b'.repeat(64), course_title: 'V5 scenario design — local QA fixture', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-scenario-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
if (process.env.REVIEW_ACCENT) await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: process.env.REVIEW_ACCENT, ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const submissions = [], records = new Map(), unexpectedWrites = []
let loseResponse = true
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/position')) {
    const body = request.postDataJSON()
    progress.learning_position = { module_id: body.module_id, lesson_id: body.lesson_id, revision: 2, content_sha256: 'c'.repeat(64), saved_at: new Date().toISOString() }
    progress.position_revision++
    progress.modules[body.module_id] = { ...progress.modules[body.module_id], learning_position: progress.learning_position }
    return route.fulfill({ json: { saved: true, enrollment_id: identity.enrollment_id, course_version: identity.course_version, learning_position: progress.learning_position, position_revision: progress.position_revision } })
  }
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.includes('/scenario-attempts/')) return route.fulfill({ json: records.get(path.split('/').at(-1)) })
  if (path.endsWith('/scenarios') && request.method() === 'POST') {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    const body = request.postDataJSON()
    submissions.push(body)
    assert.equal(body.bank_sha256, definition.bank_sha256)
    const checks = bank.questions.map(q => {
      const chosen = q.choices.find(c => c.id === body.answers[q.id])
      return { id: q.id, name: q.prompt, role: 'required', passed: chosen.id === q.correct_choice_id, detail: chosen.feedback }
    })
    const result = { passed: checks.every(check => check.passed), checks, assessment_kind: 'scenario_recognition', credit_awarded: false }
    records.set(body.request_id, { uuid: body.request_id, enrollment_id: identity.enrollment_id, module_id: bank.module_id, bank_sha256: definition.bank_sha256, answers: body.answers, result, progress_link: 'selected', read_only: true })
    progress.modules[moduleId] = { ...progress.modules[moduleId], scenario_attempt_id: body.request_id }
    if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic lost response after save' } }) }
    return route.fulfill({ json: { attempt_id: body.request_id, module_id: bank.module_id, bank_sha256: definition.bank_sha256, linked_to_progress: true, result } })
  }
  if (request.method() !== 'GET') unexpectedWrites.push(path)
  return route.fallback()
})
async function capture(id) {
  await review.capture(id, 'Actual frontend with unpublished V5 teaching/scenario fixtures; synthetic persistence and grading. Backend persistence is tested separately. No live enrollment or credit changes.')
  console.log(id)
}
try {
  await page.goto(review.baseURL + '/certification')
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  const lessonIndex = module.lessons.findIndex(lesson => lesson.id === teaching.replacements[0].id)
  await page.getByRole('button', { name: new RegExp(`^Lesson ${lessonIndex + 1}:`) }).click()
  await page.getByRole('heading', { name: teaching.replacements[0].title, exact: true }).waitFor()
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await page.getByRole('heading', { name: teaching.replacements[0].title, exact: true }).scrollIntoViewIfNeeded()
    await capture('teaching-' + width)
  }
  if (process.env.REVIEW_ALL_LESSONS === '1') {
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      for (const [index, lesson] of teaching.replacements.entries()) {
        await page.getByRole('button', { name: new RegExp(`^Lesson ${index + 1}:`) }).click()
        if (index === teaching.replacements.length - 1) await page.getByText('All lessons viewed — ready for the challenge!', { exact: true }).waitFor({ state: 'hidden' })
        const heading = page.getByRole('heading', { name: lesson.title, exact: true })
        await page.getByText('Place saved across devices.', { exact: true }).waitFor()
        await heading.evaluate(element => element.scrollIntoView({ block: 'start' }))
        const navigation = page.getByRole('navigation', { name: 'Lessons in this module', exact: true })
        assert.equal(await navigation.evaluate(element => element.scrollWidth <= element.clientWidth), true, 'Lesson navigation must wrap within the card')
        assert.equal(await page.locator('[data-cert-panel]').evaluate(element => [...element.querySelectorAll('*')].every(child => child.scrollLeft === 0)), true, 'Lesson selection must not pan the card sideways')
        const bounds = await heading.boundingBox()
        assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width, 'Lesson heading must remain inside the viewport')
        await capture(`lesson-${index + 1}-reading-${width}`)
        const question = page.getByText(lesson.knowledge_check.question, { exact: true })
        await question.scrollIntoViewIfNeeded()
        await capture(`lesson-${index + 1}-practice-${width}`)
      }
    }
  }
  if (process.env.REVIEW_ACCENT) {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('navigation', { name: 'Lessons in this module', exact: true }).scrollIntoViewIfNeeded()
    await capture('numbered-lesson-navigation-390')
  }
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await page.getByRole('heading', { name: 'Practice your judgment', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Complete Module', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Submit scenario choices', exact: true }).isDisabled(), true)
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await page.getByRole('heading', { name: 'Practice your judgment', exact: true }).scrollIntoViewIfNeeded()
    await capture('scenario-form-' + width)
  }
  await page.setViewportSize({ width: 320, height: 844 })
  await page.getByRole('heading', { name: `Module ${module.number}: ${module.title}`, exact: true }).scrollIntoViewIfNeeded()
  await capture('module-header-320')
  const stats = page.getByText(`Lessons: ${module.lessons.length}`, { exact: true }).locator('..').locator('..')
  assert.equal(await stats.evaluate(element => element.scrollWidth <= element.clientWidth), true, 'Progress row must wrap without clipping')
  await page.getByRole('radio', { name: bank.questions[0].choices[0].text, exact: true }).scrollIntoViewIfNeeded()
  await capture('scenario-choices-320')
  // Native radio keyboard navigation, using the first authored scenario.
  const question = bank.questions[0]
  const first = page.getByRole('radio', { name: question.choices[0].text, exact: true })
  await first.focus()
  await first.press('ArrowDown')
  assert.equal(await page.getByRole('radio', { name: question.choices[1].text, exact: true }).isChecked(), true)
  for (const question of bank.questions) {
    const choice = question.choices.find(choice => choice.id !== question.correct_choice_id)
    await page.getByRole('radio', { name: choice.text, exact: true }).check()
  }
  await page.getByRole('button', { name: 'Submit scenario choices', exact: true }).click()
  await page.getByText(/We could not confirm this submission/).waitFor()
  await capture('scenario-uncertain')
  await page.reload()
  await page.getByRole('button', { name: 'Open activity', exact: true }).click()
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  // The saved lesson cursor restores this module.
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  assert.equal(submissions.length, 1)
  const retry = page.getByRole('button', { name: 'Check saved scenario result', exact: true })
  await retry.scrollIntoViewIfNeeded()
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('scenario-resume-390')
  await retry.click()
  await page.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).waitFor()
  assert.equal(submissions.length, 1, 'Recovery checks must not post again')
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await page.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).scrollIntoViewIfNeeded()
    await capture('scenario-feedback-' + width)
  }
  for (const question of bank.questions) {
    const choice = question.choices.find(choice => choice.id === question.correct_choice_id)
    await page.getByRole('radio', { name: choice.text, exact: true }).check()
  }
  await page.getByRole('button', { name: 'Submit scenario choices', exact: true }).click()
  await page.getByRole('heading', { name: 'All scenario requirements met', exact: true }).waitFor()
  assert.notEqual(submissions[0].request_id, submissions[1].request_id)
  await capture('scenario-passed')
  assert.equal(progress.total_xp, 0)
  assert.deepEqual(unexpectedWrites, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  for (const capture of review.captures) {
    assert.equal(capture.pageWidth, capture.viewport.width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [], `Accessibility violations: ${capture.id}`)
  }
  review.observations.push({ id: 'scenarios', moduleId, questions: bank.questions.length, submissions: submissions.length, savedRecords: records.size, stableRetry: true, xpAwarded: 0, unexpectedWrites })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
