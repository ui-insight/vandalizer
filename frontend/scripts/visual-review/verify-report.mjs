import { chromium } from 'playwright'
import { readFile, access } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'

const path = resolve(process.argv[2] || '../artifacts/visual-review/2026-09-25/index.html')
const html = await readFile(path, 'utf8')
for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
  const link = match[1]
  if (link.startsWith('#') || /^https?:/.test(link)) continue
  await access(fileURLToPath(new URL(link, pathToFileURL(path))))
}
const browser = await chromium.launch({ headless: true, ...(process.env.REVIEW_CHROMIUM ? { executablePath: process.env.REVIEW_CHROMIUM } : {}) })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(pathToFileURL(path).href)
  await page.screenshot({ path: resolve(dirname(path), 'report-preview.png') })
  const screens = [...html.matchAll(/data-screen="([^"]+)"/g)].map(match => match[1])
  const expected = screens.filter(name => name.includes('wizard')).length
  if (!expected) throw new Error('Report has no wizard evidence')
  await page.locator('#filter').fill('wizard')
  if (await page.locator('.gallery article:visible').count() !== expected) throw new Error('Evidence filter did not return the wizard states')
  await page.locator('#filter').fill('')
  if (await page.locator('.gallery article:visible').count() !== screens.length) throw new Error('Clearing the filter did not restore all states')
  await page.setViewportSize({ width: 390, height: 844 })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  if (overflow) throw new Error('Report overflows at 390px')
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: resolve(dirname(path), 'report-preview-mobile.png') })
  if (errors.length) throw new Error(errors.join('\n'))
  console.log(JSON.stringify({ links: 'all local targets exist', galleryFilter: 'passed', reportMobileOverflow: false, browserVersion: browser.version(), pageErrors: errors }))
} finally { await browser.close() }
