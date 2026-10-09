import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const saved = JSON.parse(await readFile(new URL('../../../artifacts/visual-review/certification-completion-notices-2026-10-07/long.json', import.meta.url), 'utf8'))
const modules = JSON.parse(await readFile(new URL('../../../backend/certification-data/panel-modules.json', import.meta.url), 'utf8'))
const structure = JSON.parse(await readFile(new URL('../../../backend/certification-data/course-structure.json', import.meta.url), 'utf8'))
const identity = { enrollment_id: 'current-course-fixture', course_version: 'current-course-1', manifest_sha256: 'd'.repeat(64), course_title: 'Your current course', modules_total: modules.length, module_ids: modules.map(module => module.id), maximum_xp: 2675 }
const notice = { uuid: 'notice-fixture', id: 'notice-fixture', kind: 'certification_complete', title: saved.title, body: saved.body, link: saved.link, severity: 'info', occurrences: 1, item_kind: 'certification_credential', item_id: saved.credential_id, item_name: saved.course_title, request_uuid: null, read: false, created_at: '2026-10-07T12:00:00Z' }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Synthetic completion notice in the actual notification bell and certificate-history panel. Mark-read transport is mocked; no real notification, email or credit operation.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const writes = []
await context.route('**/api/notifications**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') { writes.push(path); notice.read = true; return route.fulfill({ json: { ok: true } }) }
  if (path.endsWith('/count')) return route.fulfill({ json: { unread_count: notice.read ? 0 : 1 } })
  return route.fulfill({ json: { notifications: [notice], unread_count: notice.read ? 0 : 1 } })
})
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET')
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...identity, id: 'current-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null } })
  if (path.endsWith('/course')) return route.fulfill({ json: { ...structure, ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(module => [module.id, []])) } })
  if (path.endsWith('/upgrade-options')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, policy: 'optional', can_activate: false, courses: [] } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [{ ...saved, provenance: 'versioned_course_completion' }] } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    notice.read = false
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/')
    if (native) await review.setBrowserZoom(2)
    await page.getByRole('button', { name: /^Notifications/ }).click()
    const item = page.getByRole('button', { name: /Certification earned:/ })
    await item.waitFor()
    await review.capture('notice-' + width)
    const box = await item.boundingBox()
    const viewport = await page.evaluate(() => innerWidth)
    assert.ok(box.x >= 0 && box.x + box.width <= viewport, JSON.stringify(box))
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/notice-${width}.axe.json`, 'utf8')), [])
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('button', { name: /^Notifications/ }).getAttribute('aria-expanded'), 'false')
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.startsWith('Notifications'))
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: 'Mark all read', exact: true }).click()
    await item.getByText('Read notification.', { exact: true }).waitFor()
    await review.capture('read-notice-' + width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/read-notice-${width}.axe.json`, 'utf8')), [])
    await item.click()
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByText('Course progress and credential', { exact: true }).click()
    const history = panel.getByRole('heading', { name: 'Your earned certificates', exact: true })
    await history.scrollIntoViewIfNeeded()
    await panel.getByText(saved.course_title, { exact: true }).waitFor()
    await review.capture('original-certificate-' + width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/original-certificate-${width}.axe.json`, 'utf8')), [])
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  assert.ok(writes.every(path => path === '/api/notifications/read-all'))
  review.observations.push({ originalCredentialDiscoverable: true, readAndUnreadContrast: true, keyboardEscapeRestoresFocus: true,
    mockNotificationReads: writes.length, certificationWrites: 0, emailSends: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
