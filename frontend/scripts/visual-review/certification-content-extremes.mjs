import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
import { keyboardJourney } from './keyboard-journey.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const module = structuredClone(modules.find(module => module.id === 'foundations'))
const longUrl = 'https://example.test/' + 'assigned-source-reference-'.repeat(10)
const variants = ['concept', 'walkthrough', 'insight', 'key-terms']
const content = [
  `A synthetic source comparison table for layout review.\n\n| Source | Recorded value | Source evidence | Decision | Next step |\n| --- | --- | --- | --- | --- |\n| Award notice | 123,456,789.00 USD | Original approved notice, page 42 | Needs review | Open the assigned source |\n| Amendment | 234,567,890.00 USD | ${longUrl} | Unresolved | Preserve both records and compare their scopes |`,
  `1. Inspect the original source.\n2. Record the exact field and source reference.\n3. Stop before any release.\n\n${String.fromCharCode(96)}source_identifier_${'original_'.repeat(12)}${String.fromCharCode(96)}\n\n[Long source reference](${longUrl})\n\n${longUrl}`,
  '> A result can be well formatted and still require source verification. Preserve unresolved facts and the decision needed before release.\n\n**A clear stopping point** remains part of the task.',
  'Source provenance — The retained original source and the exact passage used to support a value.\n\nBounded approval — Approval for the identified inputs, action and destination only.',
]
module.title = 'Source verification, conflicting program requirements and supervised delivery across multidisciplinary research administration teams'
module.xp = 999999999
module.lessons = module.lessons.slice(0, 4).map((lesson, index) => ({ ...lesson, variant: variants[index],
  title: `${variants[index]}: evaluating long source references and recorded research administration decisions`, content: content[index], diagram: undefined, knowledgeCheck: undefined }))
const identity = { enrollment_id: 'qa-content-extremes', course_version: 'synthetic-content-extremes', manifest_sha256: 'e'.repeat(64), course_title: module.title, module_ids: [module.id], modules_total: 1, maximum_xp: module.xp }
const course = { ...structure, ...identity, versioned: true, modules: [module], prerequisites: { foundations: [] } }
const progress = { ...identity, id: 'content-extremes', user_id: 'reviewer', modules: {}, total_xp: 999999999, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Synthetic content extremes in the actual course renderer; no authored-course edits, model, grading or credit.' })
const { page, context, state } = review
const journey = keyboardJourney(review)
const writes = []
const accent = process.env.REVIEW_ACCENT || '#ffffff', radius = process.env.REVIEW_RADIUS || '0px'
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: accent, ui_radius: radius, org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/position') && request.method() === 'PUT') {
    const body = request.postDataJSON(), lesson = module.lessons.find(lesson => lesson.id === body.lesson_id)
    assert.ok(lesson)
    progress.learning_position = { module_id: module.id, lesson_id: lesson.id, revision: lesson.revision, content_sha256: 'f'.repeat(64), saved_at: '2026-10-10' }
    progress.position_revision++
    return route.fulfill({ json: { saved: true, ...identity, learning_position: progress.learning_position, position_revision: progress.position_revision } })
  }
  if (request.method() !== 'GET') writes.push(path)
  return route.fallback()
})
async function inspectScrollableTable(root, id) {
  const table = root.getByRole('region', { name: 'Course table 1', exact: true })
  await journey.reach(table)
  const widths = await table.locator('th').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().width))
  const availableWidth = await table.evaluate(el => el.clientWidth)
  assert.ok(widths.every(width => width >= 140 && width <= availableWidth + 1), JSON.stringify({ widths, availableWidth }))
  for (let step = 0; step < 50; step++) {
    if (await table.evaluate(el => el.scrollLeft + el.clientWidth >= el.scrollWidth - 1)) break
    await page.keyboard.press('ArrowRight')
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)))
  }
  const scroll = await table.evaluate(el => ({ left: el.scrollLeft, client: el.clientWidth, width: el.scrollWidth }))
  assert.ok(scroll.left > 0 && scroll.left + scroll.client >= scroll.width - 1, JSON.stringify(scroll))
  review.observations.push({ id, keyboardTableScroll: scroll, columnWidths: widths })
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
}
try {
  const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
  await page.setViewportSize({ width: native ? 640 : 320, height: native ? 2200 : 1100 })
  // Plain /certification now hands off to chat; the pop-out route still shows the panel full screen.
  await page.goto(review.baseURL + '/certification?panel=fullscreen')
  if (native) await review.setBrowserZoom(2)
  if (process.env.REVIEW_TABLE_LAYOUT === 'auto') {
    const css = '.cert-table-region { container-type: inline-size; } .cert-table-region table { table-layout: auto; width: max-content; min-width: 100%; } .cert-table-region th, .cert-table-region td { min-width: min(9rem,100cqw); max-width: min(24rem,100cqw); }'
    await page.addStyleTag({ content: css })
    review.observations.push({ diagnosticOnlyCss: css })
  }
  const panel = page.locator('[data-cert-panel]')
  const position = panel.getByRole('combobox', { name: 'Learning panel position', exact: true })
  if (await position.count()) await position.selectOption('fullscreen')
  await panel.getByRole('button', { name: new RegExp(`^1 ${module.title}`) }).click()
  for (const [index, lesson] of module.lessons.entries()) {
    if (process.env.REVIEW_VARIANT && lesson.variant !== process.env.REVIEW_VARIANT) continue
    await panel.getByRole('button', { name: new RegExp(`^Lesson ${index + 1}:`) }).click()
    await panel.getByRole('heading', { name: lesson.title, exact: true }).scrollIntoViewIfNeeded()
    const id = `content-${lesson.variant}`
    await review.capture(id)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
    const bounds = await panel.locator('.cert-lesson-prose').evaluate(root => {
      const r = root.getBoundingClientRect()
      return { left: r.left, right: r.right, width: r.width, scrollWidth: root.scrollWidth, viewport: innerWidth }
    })
    review.observations.push({ variant: lesson.variant, accent, radius, bounds })
    assert.ok(bounds.left >= 0 && bounds.right <= bounds.viewport && bounds.scrollWidth <= bounds.width + 1, JSON.stringify(bounds))
    const closedTerms = panel.locator('.cert-lesson-prose details:not([open]) > summary')
    const termCount = await closedTerms.count()
    for (let term = 0; term < termCount; term++) await closedTerms.first().click()
    await panel.locator('.cert-lesson-prose').evaluate(el => el.scrollIntoView({ block: 'start' }))
    await review.capture(`${id}-body`)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}-body.axe.json`, 'utf8')), [])
    if (lesson.variant === 'concept' && process.env.REVIEW_TABLE_SCROLL === '1') {
      await inspectScrollableTable(panel, 'table-last-columns')
    }
  }
  if (process.env.REVIEW_TABLE_CHAT === '1') {
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    const lesson = module.lessons[0]
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_lesson', tool_call_id: 'table-lesson', args: {} },
      { kind: 'tool_result', tool_name: 'get_certification_lesson', tool_call_id: 'table-lesson', content: {
        ...identity, module_id: module.id, module_title: module.title, lesson_number: 1, lesson_count: module.lessons.length,
        lesson_id: lesson.id, lesson_revision: lesson.revision || 'synthetic-table', title: lesson.title, objective: lesson.objective,
        variant: lesson.variant, content: lesson.content, knowledge_check: null, diagram: null, is_last: false,
      } }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show the synthetic course table.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const card = page.locator('.cert-chat-card').last()
    await inspectScrollableTable(card, 'chat-table-last-columns')
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
