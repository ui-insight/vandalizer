import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const root = new URL('../../../backend/certification-data/courses/legacy-2026-10-02.1/', import.meta.url)
const [manifest, modules, structure] = await Promise.all(['manifest.json', 'panel-modules.json', 'course-structure.json'].map(async file => JSON.parse(await readFile(new URL(file, root), 'utf8'))))
const cases = [{ id: 'preserved-complete', count: 3, completed: 3, certified: true }, { id: 'preserved-active', count: 3, completed: 1, certified: false }, { id: 'expanded-active', count: 11, completed: 1, certified: false }]
let current = cases[0]
function course() {
  const selected = modules.slice(0, current.count)
  const ids = selected.map(module => module.id)
  return { ...structure, versioned: true, enrollment_id: current.id, course_version: `qa-course-${current.count}`, course_title: `Synthetic ${current.count}-module course`, manifest_sha256: (current.count === 3 ? 'a' : 'b').repeat(64),
    maximum_stars: 3, credit_basis: 'legacy_rubric', modules_total: current.count, module_ids: ids, modules: selected,
    maximum_xp: manifest.modules.slice(0, current.count).reduce((sum, module) => sum + module.base_xp + 3 * manifest.star_bonus_xp, 0),
    prerequisites: Object.fromEntries(manifest.modules.slice(0, current.count).map(module => [module.id, module.prerequisites])),
    tiers: structure.tiers.map(tier => ({ ...tier, moduleIds: tier.moduleIds.filter(id => ids.includes(id)) })).filter(tier => tier.moduleIds.length),
  }
}
function progress() {
  const selected = course()
  return { ...selected, id: `p-${current.id}`, user_id: 'reviewer', modules: {
    ...Object.fromEntries(selected.modules.slice(0, current.completed).map(module => [module.id, { completed: true, stars: 3, xp_earned: module.xp, attempts: 1, completed_at: '2024-01-01' }])),
    unrelated: { completed: true, stars: 3, xp_earned: 100, attempts: 1 },
  }, total_xp: 9999, level: 'architect', certified: current.certified, certified_at: current.certified ? '2024-01-01T00:00:00Z' : null, learning_position: null, position_revision: 0, unlocked: false }
}
function chat() {
  const selected = course(), saved = progress()
  return { ...selected, modules: selected.modules.map(module => ({ module_id: module.id, title: module.title, xp: module.xp, completed: saved.modules[module.id]?.completed ?? false, stars: saved.modules[module.id]?.stars ?? 0 })),
    total_xp: saved.total_xp, level: saved.level, certified: saved.certified, modules_completed: current.completed,
    next_module_id: current.certified ? null : selected.modules[current.completed].id,
  }
}
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294', evidenceMode: 'Synthetic original three-module and expanded eleven-module cohorts exercise manifest-derived home/chat/panel presentation. High XP and unrelated credit do not complete a course. No actual grades, issuance or migration.' })
const { page, context, state } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress() })
  if (path.endsWith('/course')) return route.fulfill({ json: course() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: current.id, pending: null } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    for (current of cases) {
      await page.goto(review.baseURL)
      if (native) await review.setBrowserZoom(2)
      await page.getByRole('textbox', { name: 'Message input', exact: true }).waitFor()
      if (current.certified) assert.equal(await page.getByRole('button', { name: /^Continue certification/ }).count(), 0)
      else await page.getByRole('button', { name: `Continue certification (${current.completed}/${current.count})`, exact: true }).waitFor()
      const id = `denominator-${current.id}-${width}`
      state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_progress', tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: 'get_certification_progress', tool_call_id: id, content: chat() }, { kind: 'text', content: id }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show the progress saved in this course.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      await page.getByText(id, { exact: true }).waitFor()
      const card = page.locator('.agent-tool-result').last().locator('.cert-chat-card')
      await card.waitFor()
      const chatBar = card.getByRole('progressbar', { name: 'Course modules completed' })
      assert.equal(await chatBar.getAttribute('aria-valuemax'), String(current.count))
      assert.equal(await chatBar.getAttribute('aria-valuenow'), String(current.completed))
      await capture(`${current.id}-chat-${native ? 'native' : width}`, card)
      await page.goto(review.baseURL + '/certification')
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByLabel('Your course', { exact: true }).waitFor()
      await panel.getByText('Course progress and credential', { exact: true }).click()
      if (current.certified) {
        const banner = panel.locator('[data-cert-certificate]')
        await banner.getByRole('heading', { name: 'Synthetic 3-module course', exact: true }).waitFor()
        assert.ok((await banner.innerText()).includes('3 modules completed'))
        await capture(`${current.id}-panel-${native ? 'native' : width}`, banner)
      } else {
        const bar = panel.getByRole('progressbar', { name: 'Course modules completed' })
        assert.equal(await bar.getAttribute('aria-valuenow'), String(Math.round(current.completed / current.count * 100)))
        await capture(`${current.id}-panel-${native ? 'native' : width}`, bar)
      }
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ cases, countsFromSelectedManifest: true, unrelatedCreditIgnored: true, highXpDoesNotCompleteCourse: true, reads, certificationWrites: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
