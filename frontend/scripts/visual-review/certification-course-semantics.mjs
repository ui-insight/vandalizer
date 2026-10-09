import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const all = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const lessonData = JSON.parse(await readFile(new URL('lessons.json', data), 'utf8'))
const modules = all.filter(item => ['ai_literacy', 'foundations', 'process_mapping'].includes(item.id)).map(item => ({ ...item, assessment: lessonData[item.id].assessment ?? null }))
const ai = modules.find(item => item.id === 'ai_literacy'), locked = modules.find(item => item.id === 'process_mapping')
const identity = { enrollment_id: 'qa-course-semantics', course_version: 'qa-semantics', manifest_sha256: 'd'.repeat(64), course_title: 'Course structure preview', modules_total: 3, module_ids: modules.map(item => item.id), maximum_xp: modules.reduce((sum, item) => sum + item.xp, 0) }
const course = { ...structure, ...identity, versioned: true, modules, prerequisites: { ai_literacy: [], foundations: [], process_mapping: ['ai_literacy'] } }
const progress = { ...identity, id: 'qa-semantics', user_id: 'reviewer', modules: {}, total_xp: 150, level: 'novice', certified: false, certified_at: null, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual course components with a synthetic three-module course and nonlinear prerequisite. Keyboard reflection selection, busy-state preservation, progress semantics and star names; no actual assistive technology or awarded credit.' })
const { page, context, state } = review
let theme = '#eab308', releaseSubmission
const submissions = []
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: theme, ui_radius: '12px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (req.method() === 'POST' && path.endsWith('/modules/ai_literacy/assessment')) {
    assert.equal(new URL(req.url()).searchParams.get('enrollment_id'), identity.enrollment_id)
    const body = req.postDataJSON(); submissions.push(body)
    for (const question of ai.assessment.questions) assert.ok(question.options.includes(body.answers[question.key]))
    await new Promise(resolve => { releaseSubmission = resolve })
    progress.modules.ai_literacy.self_assessment = body.answers
    return route.fulfill({ json: { ...identity, saved: true, message: 'Reflection answers saved' } })
  }
  assert.equal(req.method(), 'GET', `Unexpected write ${path}`)
  return route.fallback()
})
async function capture(name, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(name)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${name}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(name)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const [width, selectedTheme] of native ? [[640, 'gold'], [1440, 'gold'], [780, 'purple']] : [[320, 'gold'], [390, 'gold'], [768, 'gold'], [1440, 'gold'], [390, 'purple'], [1440, 'purple']]) {
    const key = `${selectedTheme}-${width}`; theme = selectedTheme === 'purple' ? '#581c87' : '#eab308'
    progress.modules = { foundations: { completed: true, stars: 2, attempts: 1, xp_earned: 150 }, ai_literacy: { completed: false, stars: 0, attempts: 0, xp_earned: 0 } }
    await page.setViewportSize({ width, height: native ? 1200 : 850 }); await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const lockedCard = panel.getByRole('button', { name: new RegExp(locked.title) })
    assert.equal(await lockedCard.isDisabled(), true)
    await lockedCard.getByText('Locked. Complete AI Literacy to unlock.', { exact: true }).waitFor()
    assert.equal(await lockedCard.getByText(locked.title, { exact: true }).isVisible(), true)
    assert.ok(await panel.getByRole('img', { name: '2 of 3 stars', exact: true }).count())
    const stageName = course.tiers.find(item => item.moduleIds.includes('foundations')).name
    const stage = panel.getByRole('progressbar', { name: `${stageName} modules completed`, exact: true })
    assert.equal(await stage.getAttribute('aria-valuenow'), '1')
    assert.equal(await stage.getAttribute('aria-valuemax'), '3')
    await capture(`locked-readable-${key}`, lockedCard)
    await panel.getByRole('button', { name: /Foundations/ }).click()
    assert.ok(await panel.getByRole('img', { name: '2 of 3 stars', exact: true }).count() >= 2)
    await capture(`module-star-labels-${key}`, panel.getByRole('heading', { name: 'Module 1: Foundations', exact: true }))
    await panel.getByRole('button', { name: 'Curriculum', exact: true }).click()
    await panel.getByRole('button', { name: 'Continue: AI Literacy', exact: true }).click()
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    const groups = panel.getByRole('radiogroup')
    assert.equal(await groups.count(), ai.assessment.questions.length)
    const submit = panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true })
    assert.equal(await submit.isDisabled(), true)
    for (const question of ai.assessment.questions) {
      const group = panel.getByRole('radiogroup', { name: question.question, exact: true })
      assert.equal(await group.getAttribute('aria-required'), 'true')
      const radio = group.getByRole('radio').first()
      await radio.focus(); await page.keyboard.press('Space'); await page.keyboard.press('ArrowDown')
      assert.equal(await group.getByRole('radio').nth(1).isChecked(), true)
    }
    await capture(`required-reflection-keyboard-${key}`, groups.last().getByRole('radio').nth(1))
    await submit.focus(); await page.keyboard.press('Space')
    await panel.getByRole('button', { name: 'Saving...', exact: true }).waitFor()
    assert.equal(await panel.getByRole('radio', { disabled: false }).count(), 0)
    assert.equal(await panel.getByRole('radio', { checked: true }).count(), ai.assessment.questions.length)
    await capture(`saving-preserves-choices-${key}`, panel.getByRole('button', { name: 'Saving...', exact: true }))
    releaseSubmission()
    const saved = panel.getByRole('heading', { name: 'Reflection answers saved', exact: true }); await saved.waitFor()
    assert.equal(progress.total_xp, 150); assert.equal(progress.modules.ai_literacy.completed, false)
    await capture(`reflection-saved-${key}`, saved)
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    const content = { ...identity, certified: false, total_xp: 150, level: 'novice', modules_completed: 1, next_module_id: 'ai_literacy', modules: modules.map(item => ({ module_id: item.id, title: item.title, xp: item.xp, completed: item.id === 'foundations', stars: item.id === 'foundations' ? 2 : 0 })) }
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_progress', tool_call_id: 'progress', args: {} }, { kind: 'tool_result', tool_name: 'get_certification_progress', tool_call_id: 'progress', content }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show course progress.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const card = page.locator('.cert-chat-card').last(), bar = card.getByRole('progressbar', { name: 'Course modules completed', exact: true })
    await bar.waitFor()
    assert.equal(await card.getByRole('img', { name: 'Completed', exact: true }).count(), 1)
    assert.equal(await card.getByRole('img', { name: 'Next module', exact: true }).count(), 1)
    assert.equal(await card.getByRole('img', { name: 'Not completed', exact: true }).count(), 1)
    assert.equal(await bar.getAttribute('aria-valuetext'), '1 of 3 modules complete')
    await capture(`chat-progress-named-${key}`, bar)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ submissions, completionWrites: 0, realCreditAwarded: false, actualScreenReader: false, keyboardChoices: true, prerequisitePolicyUnchanged: true })
} catch (error) { releaseSubmission?.(); await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
