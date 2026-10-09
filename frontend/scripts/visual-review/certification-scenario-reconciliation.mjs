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
const posts = [], reads = [], records = new Map()
let readStatus = 200
const pendingId = 'd'.repeat(32)
const answers = Object.fromEntries(bank.questions.map(q => [q.id, q.choices[0].id]))
const result = { passed: false, assessment_kind: 'scenario_recognition', credit_awarded: false,
  checks: bank.questions.map(q => ({ id: q.id, name: q.prompt, passed: false, role: 'required', detail: q.choices[0].feedback })) }
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.includes('/scenario-attempts/')) {
    assert.equal(request.method(), 'GET'); reads.push(path)
    if (readStatus !== 200) return route.fulfill({ status: readStatus, json: { detail: 'Synthetic missing or unavailable receipt' } })
    return route.fulfill({ json: records.get(pendingId) })
  }
  if (path.endsWith('/scenarios') && request.method() === 'POST') {
    const body = request.postDataJSON(); posts.push(body)
    assert.equal(body.request_id, pendingId); assert.deepEqual(body.answers, answers)
    return route.fulfill({ json: { attempt_id: pendingId, module_id: moduleId, bank_sha256: definition.bank_sha256, linked_to_progress: true, result } })
  }
  return route.fallback()
})
async function capture(id) {
  await review.capture(id, 'Actual isolated frontend; synthetic scenario receipt/response states. Real read-only HTTP persistence is verified separately on disposable MongoDB.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  await page.goto(review.baseURL + '/certification')
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    const suffix = native ? 'native' : width
    for (const state of ['selected', 'missing', 'unlinked', 'superseded', 'unavailable', 'failed_check']) {
      readStatus = state === 'missing' ? 404 : state === 'failed_check' ? 503 : 200
      records.set(pendingId, { uuid: pendingId, enrollment_id: identity.enrollment_id, module_id: moduleId,
        bank_sha256: definition.bank_sha256, answers, result, progress_link: state, read_only: true })
      await page.evaluate(({ key, value }) => { sessionStorage.clear(); sessionStorage.setItem(key, JSON.stringify(value)) },
        { key: `certification-scenarios:${identity.enrollment_id}:${moduleId}:${definition.bank_sha256}`, value: { answers, pendingId } })
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await page.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      const challenge = page.getByRole('button', { name: 'Challenge', exact: true })
      if (native) { await challenge.focus(); await challenge.press('Enter') } else await challenge.click()
      const form = page.getByRole('region', { name: 'Scenario assessment', exact: true })
      const postCount = posts.length
      await form.getByRole('button', { name: 'Check saved scenario result', exact: true }).click()
      if (['selected', 'superseded'].includes(state)) {
        await form.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).waitFor()
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved scenario result')
        if (state === 'superseded') await form.getByText(/A newer result remains selected/).waitFor()
        await form.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).scrollIntoViewIfNeeded()
      } else {
        await form.getByRole('alert').waitFor()
        await form.getByRole('alert').scrollIntoViewIfNeeded()
      }
      assert.equal(posts.length, postCount, 'Checking must never submit')
      await capture(`${state}-${suffix}`)
      if (process.env.REVIEW_REMEDIATION === '1' && ['selected', 'superseded'].includes(state)) {
        const reviewAnswer = form.getByRole('button', { name: 'Review scenario 1', exact: true })
        await reviewAnswer.focus(); await reviewAnswer.press('Enter')
        assert.ok(await page.evaluate(() => {
          const element = document.activeElement, r = element.getBoundingClientRect()
          return element instanceof HTMLInputElement && element.type === 'radio' && element.checked
            && r.top >= 56 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth
        }), 'Keyboard remediation must focus the existing selected answer inside the visible course')
        assert.equal(posts.length, postCount)
        await capture(`${state}-review-answer-${suffix}`)
      }
      if (['missing', 'unlinked'].includes(state)) {
        await form.getByRole('button', { name: state === 'missing' ? 'Retry original submission' : 'Finish linking saved result', exact: true }).click()
        await form.getByRole('button', { name: 'Submit scenario choices', exact: true }).waitFor()
        assert.equal(posts.length, postCount + 1)
      } else assert.equal(await form.getByRole('button', { name: /Retry original|Finish linking/ }).count(), 0)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ states: 6, readOnlyChecks: reads.length, explicitOriginalRetries: posts.length, xpAwarded: 0 })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
