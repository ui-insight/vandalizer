import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const readData = async name => JSON.parse(await readFile(new URL(`../../../backend/certification-data/${name}`, import.meta.url), 'utf8'))
const modules = await readData('panel-modules.json'), structure = await readData('course-structure.json')
const pdf = await readFile(new URL('../../../artifacts/visual-review/certification-credentials-2026-10-05/new-course.pdf', import.meta.url))
const selected = { enrollment_id: 'current-course', course_version: 'qa-current', course_title: 'Current course — not the earlier credential', manifest_sha256: 'a'.repeat(64) }
const earned = { enrollment_id: 'previous-course', course_version: 'legacy-2026-10-02.1', course_title: 'Vandal Workflow Architect - current course', manifest_sha256: 'b'.repeat(64) }
const original = { credential_id: 'original-credential', ...earned, learner_name: 'Alex Morgan', certified_at: '2026-10-05', provenance: 'verified_completion' }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend with synthetic completion/history responses and an existing PDF rendered by the real certificate service. GET-only original-credential download; no actual award or course migration.' })
const { page, context, state } = review
const calls = [], downloads = []
let failDownload = false, legacy = false
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  calls.push({ method: req.method(), path })
  assert.equal(req.method(), 'GET')
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...(legacy ? {} : selected), id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false } })
  if (path.endsWith('/course')) return route.fulfill({ json: { ...selected, ...structure, versioned: true, modules, prerequisites: {}, module_ids: modules.map(m => m.id), modules_total: modules.length, maximum_xp: 2675 } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [original, { ...original, ...selected, credential_id: 'other-credential' }] } })
  if (path === '/api/certification/certificate' || path.endsWith('/credentials/original-credential/certificate')) {
    if (failDownload) { failDownload = false; return route.fulfill({ status: 503, json: { detail: 'The certificate is temporarily unavailable. Try downloading again.' } }) }
    return route.fulfill({ contentType: 'application/pdf', body: pdf })
  }
  return route.fallback()
})
let sequence = 0
const completion = { module_id: 'foundations', title: 'Foundations', stars: 2, xp_earned: 100, total_xp: 300, level: 'novice', level_up: false, certified: true, modules_total: 3 }
async function send(tool, content) {
  await page.goto(review.baseURL)
  const id = `certificate-${++sequence}`
  state.chatChunks = [{ kind: 'tool_call', tool_name: tool, tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: tool, tool_call_id: id, content }, { kind: 'text', content: id }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show my saved course result.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await page.getByText(id, { exact: true }).waitFor()
  return page.locator('.cert-chat-card').last()
}
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await target.focus()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
async function download(action, id, expectedName = 'vandal-certification-original-credential.pdf') {
  const lastMessage = state.lastChat
  await action.scrollIntoViewIfNeeded(); await action.focus()
  const received = page.waitForEvent('download')
  await page.keyboard.press('Enter')
  const file = await received
  assert.equal(file.suggestedFilename(), expectedName)
  const path = `${review.out}/${id}.pdf`
  await file.saveAs(path)
  assert.deepEqual(await readFile(path), pdf)
  assert.equal(state.lastChat, lastMessage)
  downloads.push({ id, filename: expectedName, originalBytes: true })
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [640, 780] : [320, 390, 1440]) {
    await page.setViewportSize({ width, height: native ? 1000 : width < 500 ? 650 : 900 })
    legacy = false
    let card = await send('complete_certification_module', { ...completion, ...earned })
    if (native) await review.setBrowserZoom(2)
    const action = card.getByRole('button', { name: 'Download certificate (PDF)', exact: true })
    failDownload = true
    await action.click(); await card.getByRole('alert').waitFor()
    await capture(`download-failure-${width}`, action)
    await download(action, `completion-original-${width}`)
    await capture(`download-recovered-${width}`, action)
    card = await send('get_certification_progress', { ...earned, certified: true, total_xp: 300, level: 'novice', modules_total: 1, modules_completed: 1, next_module_id: null, modules: [{ module_id: 'foundations', title: 'Foundations', completed: true, stars: 2, xp: 300 }] })
    await download(card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }), `progress-original-${width}`)
    await capture(`historical-progress-${width}`, card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }))
    card = await send('complete_certification_module', { ...completion, ...earned, enrollment_id: 'missing-original' })
    await card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }).click()
    await card.getByRole('alert').waitFor()
    await capture(`missing-original-${width}`, card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }))
    card = await send('complete_certification_module', completion)
    await card.getByRole('button', { name: 'View earned certificates', exact: true }).click()
    const originalAction = card.getByRole('button', { name: `Download certificate for ${earned.course_title}`, exact: true })
    await download(originalAction, `ambiguous-history-${width}`)
    await capture(`ambiguous-history-${width}`, originalAction)
    legacy = true
    card = await send('complete_certification_module', completion)
    await download(card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }), `legacy-current-${width}`, 'vandal-workflow-architect-certificate.pdf')
    await capture(`legacy-current-${width}`, card.getByRole('button', { name: 'Download certificate (PDF)', exact: true }))
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  assert.equal(calls.some(c => c.path.includes('other-credential')), false)
  review.observations.push({ downloads, requests: calls, certificationWrites: 0, agentInvocationsForDownloads: 0, issuedCredentials: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
