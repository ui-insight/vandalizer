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

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false,
  evidenceMode: 'Frozen production frontend, two browser tabs and synthetic deterministic scenario receipts; actual deduplication tested separately through disposable MongoDB and HTTP.' })
const { page, context } = review
const posts = [], reads = []
let original = null, superseded = false
const answers = Object.fromEntries(bank.questions.map(q => [q.id, q.choices[0].id]))
const result = { passed: false, assessment_kind: 'scenario_recognition', credit_awarded: false,
  checks: bank.questions.map(q => ({ id: q.id, name: q.prompt, passed: false, role: 'required', detail: q.choices[0].feedback })) }
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.includes('/scenario-attempts/')) {
    assert.equal(request.method(), 'GET'); reads.push(path); assert.ok(path.endsWith('/' + original))
    return route.fulfill({ json: { uuid: original, enrollment_id: identity.enrollment_id, module_id: moduleId, bank_sha256: definition.bank_sha256,
      answers, result, progress_link: superseded ? 'superseded' : 'selected', read_only: true } })
  }
  if (path.endsWith('/scenarios') && request.method() === 'POST') {
    const body = request.postDataJSON(); posts.push(body); assert.deepEqual(body.answers, answers)
    const reused = original !== null
    original ||= body.request_id
    return route.fulfill({ json: { attempt_id: original, module_id: moduleId, bank_sha256: definition.bank_sha256, linked_to_progress: !superseded, reused_existing: reused, result } })
  }
  return route.fallback()
})
async function enter(target, reset = true) {
  if (reset && target.url().startsWith(review.baseURL)) await target.evaluate(() => sessionStorage.clear())
  await target.goto(review.baseURL + '/certification', { waitUntil: 'networkidle' })
  await target.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await target.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  const challenge = target.getByRole('button', { name: 'Challenge', exact: true }); await challenge.focus(); await challenge.press('Enter')
  return target.getByRole('region', { name: 'Scenario assessment', exact: true })
}
async function submit(form) {
  for (const q of bank.questions) await form.getByRole('radio', { name: q.choices[0].text, exact: true }).check()
  const button = form.getByRole('button', { name: 'Submit scenario choices', exact: true }); await button.focus(); await button.press('Enter')
  await form.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).waitFor()
}
async function capture(id) {
  await review.capture(id, 'Canonical original scenario reference and unchanged newer selection; no extra attempt, credit or assessment request on reload.')
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) for (const later of [false, true]) {
    original = null; superseded = false; posts.length = 0; reads.length = 0
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    const first = await context.newPage(); first.on('pageerror', error => review.errors.push(error.message))
    await submit(await enter(first)); superseded = later
    const form = await enter(page); await submit(form)
    await form.getByText(/These exact choices already have a saved result/).waitFor()
    assert.equal(posts.length, 2); assert.notEqual(posts[0].request_id, posts[1].request_id)
    assert.equal(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)).lastAttemptId, `certification-scenarios:${identity.enrollment_id}:${moduleId}:${definition.bank_sha256}`), original)
    if (later) await form.getByText(/A newer result remains selected/).waitFor()
    await form.getByText(/These exact choices already have a saved result/).scrollIntoViewIfNeeded()
    await capture(`duplicate-${later ? 'older' : 'selected'}-${width}`)
    const reopened = await enter(page, false)
    await reopened.getByText('Submission reference: ' + original, { exact: true }).waitFor()
    if (later) await reopened.getByText(/A newer result remains selected/).waitFor()
    assert.equal(posts.length, 2); assert.ok(reads.length >= 1)
    await reopened.getByText('Submission reference: ' + original, { exact: true }).scrollIntoViewIfNeeded()
    await capture(`reopened-${later ? 'older' : 'selected'}-${width}`)
    await first.close()
  }
  for (const item of review.captures) { assert.equal(item.pageWidth, item.viewport.width); assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), []) }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ twoBrowserTabs: true, distinctRequestIds: true, canonicalOriginalReference: true, newerSelectionPreserved: true, reloadWrites: 0, liveModels: 0 })
} catch (error) { review.observations.push({ failed: true, message: String(error) }); throw error }
finally { await review.flush(); await review.browser.close() }
