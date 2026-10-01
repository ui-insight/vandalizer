import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { items, automation } from './fixtures.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
const viewports = [[320,568],[768,600],[1440,900]].filter(([width]) => !process.env.REVIEW_WIDTHS || process.env.REVIEW_WIDTHS.split(',').includes(String(width)))
page.setDefaultTimeout(10000)
let failPicker = false, failPreview = false, failFinalUpdate = false
const creates = [], updates = []
const actionName = 'Proposal readiness review — institutional requirements, award conditions, and submission evidence'
await page.route('**/api/library/library-1/items?*', async route => {
  if (failPicker) return route.fulfill({ status: 503, json: { detail: 'Library temporarily unavailable.' } })
  const query = new URL(route.request().url()).searchParams.get('search') || ''
  const pool = [{ ...items[0], name: actionName }]
  await route.fulfill({ json: pool.filter(item => item.name.toLowerCase().includes(query.toLowerCase())) })
})
await page.route('**/api/automations/schedule/preview', async route => {
  if (failPreview) return route.fulfill({ status: 503, json: { detail: 'Schedule preview temporarily unavailable.' } })
  await route.fulfill({ json: { cron_expression: '0 9 * * 1', timezone: 'UTC', next_runs: ['2026-10-05T09:00:00Z', '2026-10-12T09:00:00Z'] } })
})
// Capture exact requests without running or delivering any automation.
await page.route('**/api/automations', async route => {
  if (route.request().method() !== 'POST') return route.fallback()
  const draft = route.request().postDataJSON(); creates.push(draft)
  state.savedAutomation = { ...automation, ...draft, id: 'auto-1', enabled: false }
  return route.fulfill({ json: state.savedAutomation })
})
await page.route('**/api/automations/auto-1', async route => {
  if (route.request().method() !== 'PATCH') return route.fallback()
  const draft = route.request().postDataJSON(); updates.push(draft)
  if (failFinalUpdate) return route.fulfill({ status: 503, json: { detail: 'Final update temporarily unavailable' } })
  state.savedAutomation = { ...state.savedAutomation, ...draft }
  return route.fulfill({ json: state.savedAutomation })
})
async function saveAndCheck(activate, width, expected) {
  const createCount = creates.length, updateCount = updates.length
  const button = page.getByRole('button', { name: activate ? 'Create & enable' : 'Save disabled', exact: true })
  failFinalUpdate = true
  await button.click()
  await page.getByRole('alert').filter({ hasText: 'Retry to update the same automation.' }).waitFor()
  assert.equal(creates.length, createCount + 1)
  const submitted = creates.at(-1)
  for (const [key, value] of Object.entries(expected)) assert.deepEqual(submitted[key], value, 'submitted ' + key)
  await shot(`wizard-${activate ? 'enable' : 'disabled'}-save-recovery-${width}`)
  failFinalUpdate = false
  await button.click()
  await page.getByRole('dialog', { name: 'New Automation', exact: true }).waitFor({ state: 'hidden' })
  assert.equal(creates.length, createCount + 1, 'Retry must not create a second automation')
  assert.equal(updates.length, updateCount + 2)
  assert.deepEqual(updates.at(-1), { ...submitted, enabled: activate })
  assert.equal(state.savedAutomation.enabled, activate)
}
async function shot(id) {
  await review.capture(id)
  console.log(`Captured ${id}`)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: page overflow`)
  const axe = JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8'))
  assert.equal(axe.length, 0, `${id}: accessibility findings ${JSON.stringify(axe)}`)
}
async function reachable(locator) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox(), viewport = page.viewportSize()
  assert.ok(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width && box.y + box.height <= viewport.height, 'Control must fit in viewport')
}
const next = () => page.getByRole('button', { name: 'Next', exact: true }).click()
const back = () => page.getByRole('button', { name: 'Back', exact: true }).click()
async function openWizard() {
  await page.goto(review.baseURL + '/?mode=automations')
  await page.getByRole('button', { name: 'New', exact: true }).click()
}
async function pickAction(width, branch) {
  await page.getByRole('button', { name: /Select Workflow/ }).click()
  const picker = page.getByRole('dialog', { name: 'Select Workflow', exact: true })
  await picker.getByRole('button', { name: actionName, exact: false }).waitFor()
  await reachable(picker.getByRole('button', { name: actionName, exact: false }))
  await shot(`wizard-${branch}-picker-${width}`)
  await picker.getByRole('button', { name: actionName, exact: false }).click()
}
try {
  if (process.env.REVIEW_ONLY !== 'api-editor') {
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height })
    await openWizard()
    await shot(`wizard-name-guidance-${width}`)
    await page.getByLabel('Name', { exact: false }).fill('Review proposal intake')
    await next()
    await shot(`wizard-trigger-${width}`)
    await next()
    await page.getByLabel('Watch Folder', { exact: false }).selectOption('folder-1')
    await page.getByLabel('Exclude Patterns', { exact: false }).fill('draft*')
    await shot(`wizard-folder-guidance-${width}`)
    await back()
    await page.getByRole('radio', { name: /API Endpoint/ }).click()
    await page.getByRole('radio', { name: /Folder Watch/ }).click()
    await next()
    assert.equal(await page.getByLabel('Watch Folder', { exact: false }).inputValue(), 'folder-1')
    assert.equal(await page.getByLabel('Exclude Patterns', { exact: false }).inputValue(), 'draft*')
    await next()
    await shot(`wizard-action-guidance-${width}`)
    await pickAction(width, 'folder')
    await next()
    await page.getByRole('checkbox', { name: 'Save results to a folder' }).check()
    await page.getByLabel('Destination folder').selectOption('folder-1')
    assert.equal(await page.getByLabel('Output format').inputValue(), 'text')
    await page.getByRole('checkbox', { name: 'Email results when complete' }).check()
    await page.getByLabel('Email recipients').fill('review@example.test')
    await reachable(page.getByRole('button', { name: 'Create & enable' }))
    await shot(`wizard-folder-review-${width}`)
    await saveAndCheck(true, width, { name: 'Review proposal intake', trigger_type: 'folder_watch', action_type: 'workflow', action_id: 'workflow-1', output_config: { storage: { enabled: true, destination_folder: 'folder-1', format: 'text' }, notifications: [{ channel: 'email', recipients: ['review@example.test'], notify_owner: true }] } })
    assert.equal(creates.at(-1).trigger_config.folder_id, 'folder-1')
    assert.equal(creates.at(-1).trigger_config.exclude_patterns, 'draft*')

    await openWizard()
    await page.getByLabel('Name', { exact: false }).fill('API proposal review')
    await next()
    await page.getByRole('radio', { name: /API Endpoint/ }).click()
    await shot(`wizard-api-guidance-${width}`)
    await next()
    await pickAction(width, 'api')
    await next()
    await reachable(page.getByRole('button', { name: 'Save disabled' }))
    await shot(`wizard-api-review-${width}`)
    await saveAndCheck(false, width, { name: 'API proposal review', trigger_type: 'api', action_type: 'workflow', action_id: 'workflow-1', output_config: {} })

    await openWizard()
    await page.getByLabel('Name', { exact: false }).fill('Scheduled proposal review')
    await next()
    await page.getByRole('radio', { name: /Schedule/ }).click()
    await next()
    await page.getByRole('combobox', { name: 'Time zone', exact: true }).selectOption('UTC')
    await page.getByLabel('Folder', { exact: true }).selectOption('folder-1')
    await page.getByText('Next run:', { exact: true }).waitFor()
    await shot(`wizard-schedule-inputs-${width}`)
    await next()
    await pickAction(width, 'schedule')
    await next()
    await reachable(page.getByRole('button', { name: 'Create & enable' }))
    await shot(`wizard-schedule-review-${width}`)
    await back(); await back()
    await page.getByRole('radio', { name: 'Monthly', exact: true }).click()
    await page.getByRole('combobox', { name: 'Day of month', exact: true }).selectOption('28')
    await page.getByRole('radio', { name: 'Specific documents', exact: true }).click()
    await page.getByRole('button', { name: 'Choose documents' }).click()
    await shot(`wizard-schedule-document-picker-${width}`)
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('dialog', { name: 'New Automation' }).count(), 1, 'Escape closes only the nested picker')
    await shot(`wizard-schedule-documents-required-${width}`)
  }
  // Recovery and search, against the same real components and controlled failures.
  await page.setViewportSize({ width: 390, height: 844 })
  await openWizard()
  await page.getByLabel('Name', { exact: false }).fill('Recovery review')
  await next(); await page.getByRole('radio', { name: /API Endpoint/ }).click(); await next()
  failPicker = true
  await page.getByRole('button', { name: /Select Workflow/ }).click()
  await page.getByRole('button', { name: 'Retry loading' }).waitFor()
  await shot('wizard-picker-error-390')
  failPicker = false
  await page.getByRole('button', { name: 'Retry loading' }).click()
  await page.getByRole('button', { name: actionName, exact: false }).waitFor()
  await page.getByLabel('Search workflows').fill('nothing matches')
  await page.getByText('No workflows matching "nothing matches"').waitFor()
  await shot('wizard-picker-no-results-390')
  await page.getByRole('button', { name: 'Clear search' }).click()
  await page.getByRole('button', { name: actionName, exact: false }).click()
  await page.getByRole('button', { name: /Select Workflow/ }).click()
  await page.getByText('Selected', { exact: true }).waitFor()
  await shot('wizard-picker-selected-390')
  await page.keyboard.press('Escape')
  assert.equal(await page.getByText('Discard this automation draft?').count(), 0, 'Picker Escape must not request draft discard')
  await back(); await page.getByRole('radio', { name: /Schedule/ }).click(); await next()
  failPreview = true
  await page.getByRole('radio', { name: 'Daily', exact: true }).click()
  await page.getByRole('button', { name: 'Retry preview' }).waitFor()
  await shot('wizard-schedule-error-390')
  failPreview = false
  await page.getByRole('button', { name: 'Retry preview' }).click()
  await page.getByText('Next run:', { exact: true }).waitFor()
  await shot('wizard-schedule-retry-390')

  }
  if (process.env.REVIEW_ONLY !== 'wizard') {
  // API guidance belongs to the created automation; keys remain placeholders.
  state.savedAutomation = { ...automation, trigger_type: 'api', trigger_config: null }
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height })
    await page.goto(review.baseURL + '/?mode=automations')
    await page.getByRole('button', { name: 'Open automation: Review incoming proposals', exact: true }).click()
    await page.getByText('API Integration', { exact: true }).scrollIntoViewIfNeeded()
    await page.getByText('Requires an API key.', { exact: false }).waitFor()
    assert.ok(await page.getByText('POST ' + review.baseURL + '/api/automations/auto-1/trigger', { exact: true }).count())
    await shot(`wizard-api-editor-python-${width}`)
    await page.getByRole('button', { name: 'cURL', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'cURL', exact: true }).getAttribute('aria-pressed'), 'true')
    assert.ok(await page.getByText('x-api-key: YOUR_API_KEY', { exact: false }).count())
    const example = page.getByRole('region', { name: 'Send files example', exact: true })
    await example.scrollIntoViewIfNeeded()
    await example.focus()
    await example.press('ArrowRight')
    await page.waitForTimeout(200)
    const scroll = await example.evaluate(element => ({ left: element.scrollLeft, width: element.scrollWidth, visible: element.clientWidth }))
    if (scroll.width > scroll.visible) assert.ok(scroll.left > 0, 'Code example must scroll from the keyboard')
    await example.press('ArrowLeft')
    await shot(`wizard-api-editor-curl-${width}`)
  }
  }
} catch (error) {
  review.errors.push(String(error)); await review.capture('wizard-continuation-blocked', String(error)); process.exitCode = 1
} finally {
  await review.flush(); await review.browser.close()
  if (review.errors.length || review.unmatched.size) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }, null, 2))
}
