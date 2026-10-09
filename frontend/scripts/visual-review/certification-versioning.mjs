import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const lessons = JSON.parse(await readFile(new URL('lessons.json', data), 'utf8'))
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const exercises = JSON.parse(await readFile(new URL('exercises.json', data), 'utf8'))
const identity = { enrollment_id: 'qa-existing-enrollment', course_version: 'qa-existing-course', manifest_sha256: 'qa-existing-digest', course_title: 'Your existing certification course', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules: modules.map(m => ({ ...m, assessment: lessons[m.id].assessment ?? null })) }
const preview = structuredClone(course)
Object.assign(preview, { enrollment_id: 'qa-preview-enrollment', course_version: 'qa-preview-course', manifest_sha256: 'qa-preview-digest', course_title: 'Optional upgrade preview — QA fixture' })
preview.modules[0].lessons[0].title = 'A lesson from the selected course'
preview.modules[0].lessons[0].content = 'This synthetic lesson verifies that the panel reads the selected course definition.'
preview.modules[0].assessment.questions[0].question = 'Selected-course reflection: what have you tried?'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5291', resetStorage: false })
const { page, context, state } = review
page.setDefaultTimeout(45000)
page.setDefaultNavigationTimeout(60000)
let progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
let activeCourse = course
let reads = 0
const writes = []
const credentialDownloads = []
const credentialPdf = await readFile(new URL('../../../artifacts/visual-review/certification-credentials-2026-10-05/legacy-unknown.pdf', import.meta.url))
const exerciseRequests = []
const completionRequests = []
const supportWrites = []
await context.route('**/api/support/**', async route => {
  if (route.request().method() !== 'GET') supportWrites.push(route.request().url())
  return route.fulfill({ json: { tickets: [], total: 0 } })
})
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [{ credential_id: 'original-credential', enrollment_id: 'earlier-course', learner_name: 'Nguyễn Văn A', course_title: 'Legacy certification - historical version unknown', course_version: null, certified_at: null, provenance: 'legacy_completion_unverified' }] } })
  if (path.endsWith('/credentials/original-credential/certificate')) { credentialDownloads.push(path); return route.fulfill({ contentType: 'application/pdf', body: credentialPdf }) }
  if (path.endsWith('/progress')) { reads++; return route.fulfill({ json: progress }) }
  if (path.endsWith('/course')) return route.fulfill({ json: activeCourse })
  const exercise = path.match(/\/modules\/([^/]+)\/exercise/)
  if (exercise) { exerciseRequests.push(url.searchParams.get('enrollment_id')); return route.fulfill({ json: exercises[exercise[1]] }) }
  if (request.method() !== 'GET') {
    writes.push({ path, enrollment: url.searchParams.get('enrollment_id'), body: request.postDataJSON() })
    if (path.endsWith('/provision')) {
      progress.modules.foundations = { provisioned_docs: ['synthetic-lab-document'] }
      return route.fulfill({ json: { provisioned_docs: ['synthetic-lab-document'] } })
    }
    if (path.endsWith('/validate')) return route.fulfill({ json: { passed: true, stars: 1, checks: [
      { name: 'Run completed', passed: true, detail: 'The saved workflow produced output for the selected documents.' },
      { name: 'Source review', passed: false, detail: 'Compare each extracted budget restriction with the cited source passage before sharing the result with a colleague.' },
    ] } })
    if (path.endsWith('/complete')) {
      const requestId = url.searchParams.get('request_id')
      completionRequests.push(requestId)
      assert.match(requestId, /^[a-f0-9]{32}$/)
      if (completionRequests.length === 1) return route.fulfill({ status: 503, json: { detail: 'Synthetic uncertain completion response' } })
      assert.equal(requestId, completionRequests[0])
      progress.modules.foundations = { ...progress.modules.foundations, completed: true, stars: 1, attempts: 1, xp_earned: 125 }
      progress.total_xp = 125
      return route.fulfill({ json: { ...preview, module_id: 'foundations', stars: 1, xp_earned: 125, total_xp: 125, level: 'novice', level_up: false, certified: false, attempt_id: requestId, validation: { passed: true, stars: 1, checks: [] } } })
    }
    if (path.endsWith('/position')) {
      const body = request.postDataJSON()
      if (body.expected_revision !== progress.position_revision) return route.fulfill({ status: 409, json: { detail: 'Your saved place changed in another session' } })
      progress.learning_position = { module_id: body.module_id, lesson_id: body.lesson_id, revision: 1, content_sha256: 'qa-content', saved_at: new Date().toISOString() }
      progress.position_revision++
      progress.modules[body.module_id] = { ...progress.modules[body.module_id], learning_position: progress.learning_position }
      return route.fulfill({ json: { saved: true, enrollment_id: progress.enrollment_id, course_version: progress.course_version, learning_position: progress.learning_position, position_revision: progress.position_revision } })
    }
    if (path.endsWith('/assessment')) {
      const moduleId = path.split('/')[4]
      progress.modules[moduleId] = { self_assessment: request.postDataJSON().answers }
      return route.fulfill({ json: { stored: true, enrollment_id: progress.enrollment_id } })
    }
  }
  return route.fallback()
})
let sequence = 0
async function send(name, content) {
  const id = 'versioning-' + ++sequence
  state.chatChunks = [{ kind: 'tool_call', content: '', tool_name: name, tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: name, tool_call_id: id, content }, { kind: 'text', content: id }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Review this course state.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await page.getByText(id, { exact: true }).waitFor()
}
async function home() { await page.goto(review.baseURL, { waitUntil: 'domcontentloaded' }); await page.getByRole('textbox', { name: 'Message input', exact: true }).waitFor() }
async function capture(id) { await review.capture(id, 'Synthetic course/API responses and actual frontend interactions; no live model, migration or publication.'); console.log(id) }
const passed = { ...identity, module_id: 'ai_literacy', title: 'AI Literacy', passed: true, stars: 3, checks: [{ name: 'Reflection saved', passed: true, detail: 'Synthetic passing result for action-state QA.' }] }

try {
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await home()
    await send('check_certification_module', { ...passed, enrollment_id: 'qa-old-enrollment' })
    const submit = page.getByRole('button', { name: 'Complete the module', exact: true })
    assert.equal(await submit.isDisabled(), true)
    await submit.scrollIntoViewIfNeeded()
    await capture('stale-card-' + width)
    const before = reads
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/certification/progress'))
    await page.getByRole('button', { name: 'Refresh progress', exact: true }).click()
    await refreshed
    assert.equal(writes.length, 0)
    assert.ok(reads > before)
  }
  await home()
  await send('check_certification_module', passed)
  assert.equal(await page.getByRole('button', { name: 'Complete the module', exact: true }).isEnabled(), true)
  await capture('current-card-1440')
  await home()
  const lesson = lessons.ai_literacy.lessons[2]
  await send('get_certification_lesson', { ...identity, ...lesson, module_id: 'ai_literacy', module_title: 'AI Literacy', lesson_number: 3, lesson_count: 9, is_last: false })
  await page.getByRole('radio', { name: lesson.knowledge_check.options.find(o => o.correct).text, exact: true }).check()
  await page.getByRole('button', { name: 'Check answer', exact: true }).click()
  await capture('current-course-practice')

  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByText('Course progress and credential', { exact: true }).click()
  await page.getByText('/ 2675 XP', { exact: false }).waitFor()
  await capture('versioned-panel-overview')
  await page.getByRole('button', { name: /^0 AI Literacy/ }).click()
  await page.getByRole('button', { name: /^Lesson 3:/ }).click()
  await page.getByText('Place saved across devices.', { exact: true }).waitFor()
  await capture('versioned-panel-lesson')
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) if (key.startsWith('cert-lesson:') || key.startsWith('cert-active-module:')) localStorage.removeItem(key)
  })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await page.getByText('Lesson 3 of 9', { exact: true }).waitFor()
  await capture('versioned-panel-resume')

  // A different session changed the server cursor after this panel loaded.
  progress.position_revision++
  progress.learning_position = { ...progress.learning_position, lesson_id: lessons.ai_literacy.lessons[4].id }
  progress.modules.ai_literacy.learning_position = progress.learning_position
  await page.getByRole('button', { name: /^Lesson 4:/ }).click()
  await page.getByText(/Your place could not be saved/).waitFor()
  await capture('position-conflict')
  const writesBeforeRefresh = writes.length
  await page.getByRole('button', { name: 'Refresh progress', exact: true }).click()
  await page.getByText('Lesson 5 of 9', { exact: true }).waitFor()
  assert.equal(writes.length, writesBeforeRefresh)
  await page.getByRole('button', { name: 'Save this place', exact: true }).click()
  await page.getByText('Place saved across devices.', { exact: true }).waitFor()
  await capture('position-conflict-resolved')

  activeCourse = preview
  progress = { ...progress, ...preview, learning_position: null, position_revision: 0, modules: {}, id: 'qa-preview-progress' }
  delete progress.versioned
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await page.getByText('Course progress and credential', { exact: true }).click()
  await page.getByRole('heading', { name: 'Your earned certificates', exact: true }).waitFor()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download certificate for Legacy certification - historical version unknown', exact: true }).click()
  assert.equal((await downloaded).suggestedFilename(), 'vandal-certification-original-credential.pdf')
  assert.equal(credentialDownloads.length, 1)
  await capture('historical-certificate-after-course-change')
  await page.getByRole('button', { name: /^0 AI Literacy/ }).click()
  await page.getByRole('heading', { name: 'A lesson from the selected course', exact: true }).waitFor()
  await capture('different-course-teaching')
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await page.getByText('Selected-course reflection: what have you tried?', { exact: false }).waitFor()
  for (const question of preview.modules[0].assessment.questions) {
    await page.getByRole('radio', { name: question.options[0], exact: true }).check()
  }
  await page.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).click()
  await page.getByRole('heading', { name: 'Reflection answers saved', exact: true }).waitFor()
  await capture('versioned-reflection-saved')
  const reflections = writes.filter(write => write.path.endsWith('/assessment'))
  assert.equal(reflections.length, 1)
  assert.equal(reflections[0].enrollment, preview.enrollment_id)
  const positions = writes.filter(write => write.path.endsWith('/position'))
  assert.equal(positions.length, 3)
  assert.ok(positions.every(write => write.enrollment === course.enrollment_id))
  assert.equal(progress.total_xp, 0)
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByRole('button', { name: /^1 Foundations/ }).click()
  await page.getByRole('button', { name: 'Set Up Lab', exact: true }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  assert.equal(await page.locator('em').filter({ hasText: 'What documents do I have about NSF proposals?' }).count(), 1)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('em').filter({ hasText: 'What documents do I have about NSF proposals?' }).scrollIntoViewIfNeeded()
  await capture('panel-exercise-markdown-390')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await capture('panel-exercise-markdown-1440')
  await page.getByRole('button', { name: 'Complete Module', exact: true }).click()
  await page.getByText('Completion could not be confirmed. Resume the original request to finish or retrieve its saved result.', { exact: true }).waitFor()
  await capture('completion-response-uncertain')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  // Resume is visible even without a saved lesson position, including when
  // an uncertain request already awarded credit and hid Complete Module.
  await page.getByRole('region', { name: 'Pending certification completion' }).waitFor()
  assert.equal(completionRequests.length, 1)
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('pending-completion-resume-390')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await capture('pending-completion-resume-1440')
  await page.getByRole('button', { name: 'Resume original completion', exact: true }).click()
  await page.getByRole('heading', { name: 'Module Complete!', exact: true }).waitFor()
  await capture('completion-recovered-after-reload')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByRole('button', { name: /Foundations Documents In/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const firstStep = page.getByRole('heading', { name: 'Exercise Steps', exact: true }).locator('..').locator('ol > li').first()
  assert.equal(await firstStep.locator('span').first().textContent(), '1')
  await firstStep.scrollIntoViewIfNeeded()
  await capture('completed-procedure-numbers')
  progress.pending_completions = [{ attempt_id: 'c'.repeat(32), module_id: 'foundations', state: 'evaluating', in_flight: true }]
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByText('Your submission is still being processed. Refresh its status before trying again.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Resume original completion', exact: true }).count(), 0)
  await capture('pending-evaluation-in-flight-390')
  progress.pending_completions[0].in_flight = false
  await page.getByRole('button', { name: 'Refresh status', exact: true }).click()
  await page.getByText('This submission needs review before it can continue. Your existing credit is preserved.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Resume original completion', exact: true }).count(), 0)
  await capture('pending-evaluation-needs-review-390')
  const writesBeforeHelp = writes.length
  await page.getByRole('button', { name: 'Prepare support request', exact: true }).click()
  const support = page.getByRole('region', { name: 'Support', exact: true })
  await support.getByLabel('Description', { exact: true }).waitFor()
  assert.equal(await page.getByRole('dialog', { name: 'Learning and certification' }).count(), 0)
  const draft = await support.getByLabel('Description', { exact: true }).inputValue()
  assert.ok(draft.includes(`Enrollment: ${preview.enrollment_id}`))
  assert.ok(draft.includes(`Assessment reference: ${'c'.repeat(32)}`))
  await capture('assessment-support-draft-390')
  await support.getByLabel('Description', { exact: true }).fill(draft + '\nMy added details.')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await capture('assessment-support-edited-draft-1440')
  await support.getByRole('button', { name: 'Close support', exact: true }).click()
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare support request', exact: true }).click()
  await support.getByLabel('Description', { exact: true }).waitFor()
  assert.equal(await support.getByLabel('Description', { exact: true }).inputValue(), draft + '\nMy added details.')
  assert.equal(writes.length, writesBeforeHelp)
  assert.deepEqual(supportWrites, [])
  await support.getByRole('button', { name: 'Close support', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  progress.pending_completions[0].state = 'graded'
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('region', { name: 'Pending certification completion' }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Resume original completion', exact: true }).count(), 1)
  await capture('bookmark-saved-grade-resume-390')
  await page.getByRole('button', { name: 'Open module', exact: true }).click()
  progress.pending_completions = []
  await page.getByRole('button', { name: 'Refresh status', exact: true }).click()
  await page.getByRole('region', { name: 'Pending certification completion' }).waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await page.getByRole('button', { name: 'Check Progress', exact: true }).click()
  const feedback = page.locator('[data-cert-panel]').getByRole('status').filter({ hasText: 'Module requirements met' })
  await feedback.waitFor()
  assert.equal(await feedback.getByText('All checks passed', { exact: true }).count(), 0)
  assert.equal(await feedback.getByText('Not met', { exact: false }).count() > 0, true)
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await feedback.scrollIntoViewIfNeeded()
    await capture('mixed-check-results-' + width)
  }
  assert.equal(completionRequests.length, 2)
  assert.equal(completionRequests[0], completionRequests[1])
  assert.equal(progress.total_xp, 125)
  assert.ok(exerciseRequests.every(id => id === course.enrollment_id || id === preview.enrollment_id))
  review.observations.push({ id: 'versioned-delivery', reads, writes, exerciseRequests, credentialDownloads, completionRequests, note: 'The optional selection switch is a synthetic server fixture, not an implemented migration UI. Server-position fixtures verify local-storage-independent resume and explicit conflict recovery; actual server persistence has separate integration evidence. Migration remains open.' })
  for (const capture of review.captures) {
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [], `Accessibility violations in ${capture.id}`)
  }
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
} catch (error) {
  await capture('blocked')
  throw error
} finally {
  await review.flush()
  await review.browser.close()
}
