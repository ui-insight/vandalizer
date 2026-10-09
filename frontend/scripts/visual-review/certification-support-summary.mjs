import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Synthetic read-only support presentation. Exact ownership, privacy, bounded history and non-mutation separately verified using disposable MongoDB.' })
const { page, context } = review
const base = { user_id: 'learner', name: 'Alex Morgan', email: 'learner@example.test', progress_id: 'progress', enrollment_id: 'a'.repeat(32),
  course_title: 'Agentic certification', course_version: 'v5.0-qa', enrollment_state: 'active', is_active: true, can_unlock: false,
  learning_order: 'any_order', level: 'novice', total_xp: 150, modules_completed: 1, modules_total: 11, certified: false,
  certified_at: null, last_activity_date: null, unlocked: false, updated_at: null }
const summary = { read_only: true, observed_at: '2026-10-08T10:00:00+00:00', position_status: 'saved',
  last_saved_lesson: { module_id: 'ai_literacy', module_title: 'AI Literacy', lesson_id: 'limits', lesson_title: 'Recognizing the limits of generated answers', revision: 2, saved_at: null },
  pending_credential: false, explanation: 'Recorded state only. Refresh for current status; opening this view does not retry, grade or change a course.',
  pending_completions: [], recent_completions: [], older_completions_available: false }
const history = [{ attempt_id: 'b'.repeat(32), module_id: 'ai_literacy', module_title: 'AI Literacy', state: 'rejected', created_at: '2026-10-08T09:30:00+00:00',
  next_step: 'Required checks were not met. Open the original feedback, revise the evidence and submit a new assessment.',
  selected_evidence: { review_attempt_id: 'c'.repeat(32), scenario_attempt_id: 'd'.repeat(32) },
  failed_required_outcomes: [{ outcome_id: 'ai_literacy.limits', statement: 'Explain where generated answers need verification and choose a safe next step before relying on them.' }] }]
let mode = 'ready'
const row = () => mode === 'legacy' ? { ...base, enrollment_id: null, course_version: null, is_active: null, course_title: 'Legacy course — historical version unknown' } : base
const detail = () => ({ ...row(), ...(mode === 'mismatched' ? { enrollment_id: 'wrong' } : {}), modules: {}, support_summary: {
  ...summary,
  ...(mode === 'operations' ? { operations: { worker_marked_in_flight: true, course_change_pending: true, groups: [
    { kind: 'automatic_review', more_pending: true, more_recent: true, records: [
      { request_id: '1'.repeat(32), module_title: 'Foundations', state: 'grading_unavailable', next_step: 'Automatic grading was unavailable. This is not a learner failure. Use the learner’s technical recovery or retry for the same saved evidence; staff grading is not required.', references: { parent_attempt_id: '2'.repeat(32) } },
      { request_id: '3'.repeat(32), module_title: 'Foundations', state: 'revision_required', next_step: 'Open the original feedback and revise the identified evidence.', failed_required_outcomes: [{ outcome_id: 'foundations.verify', statement: 'Verify reported values against the source before relying on the result.' }] },
    ] },
    { kind: 'lab_run', more_pending: false, more_recent: true, records: [
      { request_id: '4'.repeat(32), module_title: 'Connected workflow', state: 'uncertain', next_step: 'The run outcome is uncertain. Check saved results and stage receipts before any retry to avoid duplicate work.', references: { input_snapshot_id: '5'.repeat(32) } },
      { state: 'unavailable', next_step: 'This original operation needs reconciliation. No result, evidence or safe retry is inferred.' },
    ] },
    { kind: 'private_handoff', more_pending: false, more_recent: true, records: [
      { request_id: '6'.repeat(32), module_title: 'Output delivery', state: 'delivered', next_step: 'The approved copy is saved in the learner’s private training inbox. This is not sponsor delivery, external email or broader sharing.', references: { previous_failed_id: '7'.repeat(32), review_id: '8'.repeat(32) } },
      { request_id: '7'.repeat(32), module_title: 'Output delivery', state: 'failed', next_step: 'The controlled training handoff stopped before writing a destination copy. Generation is preserved. The learner can inspect this exact failed receipt and retry only its approved private handoff.' },
    ] },
  ] } } : {}),
  ...(mode === 'pending' ? { pending_credential: true, pending_completions: [{ attempt_id: 'e'.repeat(32), module_id: 'ai_literacy', module_title: 'AI Literacy', state: 'graded', in_flight: true,
    next_step: 'The original grade is saved; completion is not yet confirmed. Recover that same request.' }] } : {}),
  ...(mode === 'history' ? { recent_completions: history, older_completions_available: true } : {}),
  ...(mode === 'legacy' ? { position_status: 'not_recorded', last_saved_lesson: null, explanation: 'Historical course version is unknown. Reading position may exist only in the learner’s browser; no server assessment history is inferred.' } : {}),
  ...(mode === 'unavailable' ? { position_status: 'unavailable', last_saved_lesson: null, recent_completions: [{ state: 'unavailable', next_step: 'An original completion record needs reconciliation; no grade or evidence is inferred.' }] } : {}),
} })
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false } }))
await context.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Staff reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
const reads = []
await context.route('**/api/admin/**', route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: [row()], total: 1, capped: false } })
  if (path === '/api/admin/certifications/learner') {
    assert.equal(url.searchParams.get('enrollment_id'), row().enrollment_id)
    return mode === 'error' ? route.fulfill({ status: 503, json: { detail: 'Saved learning status is temporarily unavailable.' } }) : route.fulfill({ json: detail() })
  }
  if (path === '/api/admin/system/version') return route.fulfill({ json: { current: '5.0.0', update_available: false } })
  if (path === '/api/admin/catalog/status') return route.fulfill({ json: { update_available: false } })
  if (path === '/api/admin/telemetry/optin') return route.fulfill({ json: { show_banner: false } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    for (mode of ['ready', 'pending', 'history', 'operations', 'legacy', 'unavailable', 'error', 'mismatched']) {
      await page.goto(review.baseURL + '/admin?tab=certifications')
      if (native) await review.setBrowserZoom(2)
      const trigger = page.getByRole('button', { name: /View learning status for/ })
      await trigger.click()
      const region = page.getByRole('region', { name: 'Learning status: Alex Morgan', exact: true })
      await region.getByRole('button', { name: 'Refresh learning status' }).waitFor()
      await page.waitForFunction(() => !document.body.textContent.includes('Loading saved learning status'))
      assert.equal(await region.evaluate(node => document.activeElement === node), true)
      await region.getByRole('heading', { name: 'Learning status: Alex Morgan', exact: true }).scrollIntoViewIfNeeded()
      await capture(`${mode}-${native ? 'native' : width}`)
      if (mode === 'operations') {
        await region.getByRole('heading', { name: 'Automatic assessments, runs and handoffs', exact: true }).scrollIntoViewIfNeeded()
        await capture(`operations-state-${native ? 'native' : width}`)
        const references = region.getByText('Saved operation references', { exact: true }).first()
        await references.focus(); await page.keyboard.press('Enter')
        await region.getByText('2'.repeat(32), { exact: true }).waitFor({ state: 'visible' })
        await references.scrollIntoViewIfNeeded()
        await capture(`operations-references-${native ? 'native' : width}`)
        await region.getByRole('heading', { name: 'Lab runs', exact: true }).scrollIntoViewIfNeeded()
        await capture(`operations-runs-${native ? 'native' : width}`)
        await region.getByRole('heading', { name: 'Private training handoffs', exact: true }).scrollIntoViewIfNeeded()
        await capture(`operations-handoffs-${native ? 'native' : width}`)
        const handoff = region.getByRole('article').filter({ hasText: 'Output delivery · Private training copy saved' })
        await handoff.getByText('Saved operation references', { exact: true }).focus(); await page.keyboard.press('Enter')
        await handoff.getByText('8'.repeat(32), { exact: true }).waitFor({ state: 'visible' })
        await handoff.getByText('Original failed handoff', { exact: true }).scrollIntoViewIfNeeded()
        await capture(`operations-handoff-references-${native ? 'native' : width}`)
      }
      if (mode === 'history') {
        const disclosure = region.getByText('Original request references', { exact: true })
        await disclosure.focus(); await page.keyboard.press('Enter')
        await region.getByText('c'.repeat(32), { exact: true }).waitFor({ state: 'visible' })
        await disclosure.scrollIntoViewIfNeeded()
        await capture(`history-references-${native ? 'native' : width}`)
      }
      if (mode === 'error') {
        mode = 'ready'
        await region.getByRole('button', { name: 'Refresh learning status' }).click()
        await region.getByText('AI Literacy · Recognizing the limits of generated answers', { exact: true }).waitFor()
        await region.getByRole('heading', { name: 'Learning status: Alex Morgan', exact: true }).scrollIntoViewIfNeeded()
        await capture(`refresh-recovered-${native ? 'native' : width}`)
      }
      await region.getByRole('button', { name: 'Close status' }).click()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.startsWith('View learning status for'))
    }
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ adminWrites: 0, exactEnrollmentReads: true, keyboardDisclosure: true, focusReturned: true, failureRefresh: true, reads })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
