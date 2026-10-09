import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { readFile, writeFile, mkdir, access } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'
const report = resolve('../docs/reviews/certification-v5-evidence-ledger.html')
const html = await readFile(report, 'utf8')
const ledger = JSON.parse(await readFile(report.replace(/html$/, 'json'), 'utf8'))
for (const match of html.matchAll(/href="([^"]+)"/g)) await access(fileURLToPath(new URL(match[1], pathToFileURL(report))))
const out = resolve(process.env.REVIEW_OUTPUT || '../artifacts/visual-review/certification-evidence-ledger-2026-10-09/browser')
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true, executablePath: process.env.REVIEW_CHROMIUM })
const errors = [], captures = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.on('pageerror', error => errors.push(String(error)))
  await page.route('http://**/*', route => route.abort())
  await page.route('https://**/*', route => route.abort())
  await page.goto(pathToFileURL(report).href)
  await page.addScriptTag({ path: resolve('node_modules/axe-core/axe.min.js') })
  assert.equal(await page.locator('tbody tr').count(), ledger.counts.browser_runs)
  for (const width of [1440, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: resolve(out, `overview-${width}.png`) })
    const filter = page.getByRole('searchbox', { name: 'Filter by checkpoint, state family, browser or evidence directory' })
    await filter.fill('scenario-reconciliation')
    assert.equal(await page.locator('tbody tr:visible').count(), 2)
    await page.locator('#count').scrollIntoViewIfNeeded()
    await page.screenshot({ path: resolve(out, `filtered-${width}.png`) })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    const axe = await page.evaluate(async () => (await window.axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] })).violations)
    await writeFile(resolve(out, `ledger-${width}.axe.json`), JSON.stringify(axe, null, 2))
    assert.deepEqual(axe, [])
    await filter.fill('no-matching-certification-run')
    assert.equal(await page.locator('tbody tr:visible').count(), 0)
    await filter.fill('')
    assert.equal(await page.locator('tbody tr:visible').count(), ledger.counts.browser_runs)
    captures.push({ width, search: 'passed', pageOverflow: false, axeViolations: 0 })
  }
  assert.deepEqual(errors, [])
  await writeFile(resolve(out, 'report-ui.json'), JSON.stringify({ localLinks: 'all available', captures, errors, baselineCaptures: ledger.counts.baseline_selected_captures }, null, 2))
  console.log(JSON.stringify({ rows: ledger.counts.browser_runs, localLinks: 'passed', captures, errors }))
} finally { await browser.close() }
