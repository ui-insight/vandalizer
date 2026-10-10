import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { docs } from './fixtures.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT || '/tmp/vandalizer-home-review', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5187' })
const { page, state } = review
page.setDefaultTimeout(60000)
page.setDefaultNavigationTimeout(60000)
let populated = false, empty = false, evidenceError = false
let notice = { uuid: 'notice-1', item_kind: 'search_set', item_id: 'set-1', item_name: 'test', severity: 'warning', alert_type: 'regression', message: 'Quality dropped by 10.0 points (95.0 -> 85.0)', previous_score: 95, current_score: 85, created_at: '2026-10-09T12:00:00Z', review_state: 'new' }
const onboarding = () => ({ first_session_completed: true, has_documents: !empty, has_workflows: !empty, has_extraction_sets: !empty, has_library_items: !empty, has_pinned_item: false, has_favorited_item: false, has_team_members: true, has_automations: false, has_enabled_automation: false, has_knowledge_base: !empty, has_ready_knowledge_base: !empty, has_run_workflow: !empty, has_chatted_with_docs: !empty, has_conversations: !empty, is_certified: false, has_only_onboarding_docs: false, maturity_stage: 'practitioner', suggestion_pills: ['Run test on your latest documents'], daily_guidance: 'Your test flagged a quality warning — want me to take a look?', unprocessed_doc_count: 3, recent_documents: empty ? [] : docs.slice(0, 2), recent_activity: populated ? [{ id: 'activity-1', type: 'workflow_run', item_kind: 'workflow', item_id: 'workflow-1', title: 'Community resilience budget review', status: 'running', relative_time: '12 minutes ago' }] : [], active_alerts: empty || notice.review_state === 'acknowledged' ? [] : [notice, notice] })
await page.route('**/api/config/onboarding-status', route => route.fulfill({ json: onboarding() }))
await page.route('**/api/obligations', route => route.fulfill({ json: { inbox_hidden: false, items: populated ? [{ uuid: 'ob-1', project_uuid: 'project-1', project_title: 'Community resilience proposal', kind: 'deadline', title: 'Sponsor submission', deadline_type: 'sponsor_submission', due_at: '2026-10-15T17:00:00', due_text: '5 p.m. Pacific', status: 'open', dismissed: false, in_conflict: false, sources: [{ document_uuid: 'doc-0', document_title: 'Proposal narrative.pdf', page: 2, quote: 'Submit by October 15 at 5 p.m. Pacific.', role: 'evidence' }] }] : [] } }))
await page.route('**/api/reviews?status=pending', route => route.fulfill({ json: { reviews: populated ? [{ uuid: 'review-1', workflow_name: 'Award terms review', step_name: 'Approve summary', status: 'pending' }] : [] } }))
await page.route('**/api/config/home-alerts/notice-1/evidence', route => evidenceError ? route.fulfill({ status: 503, json: { detail: 'Unavailable' } }) : route.fulfill({ json: { linked_run: false, runs: [{ uuid: 'eval-1', created_at: '2026-10-09T11:50:00Z', score: 85, model: 'Review model', source: 'validation', num_test_cases: 4, num_runs: 3, accuracy: .85, consistency: .9, num_checks: 0, checks_failed: 0, score_breakdown: { raw_score: 87, sample_size_factor: 1 }, extraction_config: { mode: 'single_pass' }, result_snapshot: { test_cases: [{ label: 'Award notice', fields: [{ field_name: 'End date', expected: '2027-09-30', most_common_value: '2026-09-30', accuracy: 0 }] }] } }] } }))
await page.route('**/api/config/home-alerts/notice-1', route => { notice = { ...notice, review_state: route.request().postDataJSON().state }; return route.fulfill({ json: notice }) })
async function capture(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': horizontal overflow')
  const violations = JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8'))
  assert.deepEqual(violations, [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  await page.goto(review.baseURL + '/?mode=chat')
  await page.getByRole('heading', { name: 'Your workspace', exact: true }).waitFor()
  assert.equal(await page.getByText('test', { exact: true }).count(), 1)
  assert.equal(await page.getByRole('button', { name: /Run test/ }).count(), 0)
  await capture('home-warning-desktop')
  evidenceError = true
  await page.getByRole('button', { name: 'View evaluation details' }).click()
  await page.getByRole('button', { name: 'Retry evaluation history' }).waitFor()
  evidenceError = false
  await page.getByRole('button', { name: 'Retry evaluation history' }).click()
  await page.getByText('4 test cases · 3 runs · Model: Review model', { exact: true }).waitFor()
  await page.getByText('Test case: Award notice').click()
  await capture('home-evaluation-details')
  await page.getByRole('button', { name: 'Mark under review' }).click()
  await page.getByText('Extraction template · Warning · Under review', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Acknowledge notice' }).click()
  await page.getByRole('region', { name: 'Tool quality notices' }).waitFor({ state: 'hidden' })
  assert.equal(state.lastChat, undefined)
  notice.review_state = 'new'; populated = true
  await page.goto(review.baseURL + '/?mode=chat')
  await page.getByRole('region', { name: 'Pending approvals' }).waitFor()
  assert.ok(await page.getByRole('region', { name: 'RA inbox' }).evaluate(el => !!(el.compareDocumentPosition(document.querySelector('.home-quality')) & Node.DOCUMENT_POSITION_FOLLOWING)))
  await capture('home-work-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('home-work-mobile')
  await page.getByRole('button', { name: 'Select document: Proposal narrative.pdf' }).click()
  await page.getByRole('heading', { name: 'Your workspace', exact: true }).waitFor({ state: 'hidden' })
  assert.equal(state.lastChat, undefined, 'Selecting a source must not send a message or execute a run')
  assert.equal(await page.getByRole('button', { name: /Your test flagged|Quality dropped/ }).count(), 0, 'Selecting a source must not resurrect the old duplicate warning briefing')
  await capture('home-document-selected-mobile')
  empty = true; populated = false
  await page.goto(review.baseURL + '/?mode=chat')
  await page.getByRole('heading', { name: 'Your workspace', exact: true }).waitFor()
  assert.equal(await page.getByRole('region', { name: 'Tool quality notices' }).count(), 0)
  await capture('home-empty-mobile')
  assert.deepEqual([...review.unmatched], [])
  // The intentional HTTP 503 is recorded by some browsers as a console error.
  assert.ok(review.errors.every(e => JSON.stringify(e).includes('503')), JSON.stringify(review.errors))
} finally { await review.flush(); await review.browser.close() }
