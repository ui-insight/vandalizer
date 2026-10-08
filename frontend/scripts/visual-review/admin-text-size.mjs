import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
const fixed = {
  '/api/auth/me': { id: 'reviewer', user_id: 'reviewer', name: 'Alex Morgan', email: 'reviewer@example.test', is_admin: true, current_team: 'team-1' },
  '/api/auth/config': { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false },
  '/api/admin/system/version': { current: '5.0.0', update_available: false },
  '/api/admin/catalog/status': { update_available: false },
  '/api/admin/telemetry/optin': { show_banner: false },
  '/api/admin/users': { items: [], total: 0, capped: false },
  '/api/admin/users/isolated': { items: [], total: 0, capped: false },
}
await page.route('**/api/**', route => {
  const path = new URL(route.request().url()).pathname.replace(/\/$/, '')
  return path in fixed ? route.fulfill({ json: fixed[path] }) : route.fallback()
})

try {
  for (const width of [1440, 1024, 900, 899, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(review.baseURL + '/admin?tab=users')
    await page.getByRole('heading', { name: 'Admin', exact: true }).waitFor()
    const normalWidth = await page.locator('.section-page__nav').evaluate(el => el.getBoundingClientRect().width)
    // Regression simulation for navigation text only. Native Safari's text-size
    // command is checked separately; CSS font scaling is not browser text zoom.
    await page.locator('.section-page__nav').evaluate(nav => {
      const elements = [...nav.querySelectorAll('h1, p, button, label, select')]
      const sizes = elements.map(el => parseFloat(getComputedStyle(el).fontSize))
      elements.forEach((el, index) => { el.style.fontSize = `${sizes[index] * 2}px` })
    })
    const metrics = await page.locator('.section-page__nav').evaluate(nav => {
      const box = nav.getBoundingClientRect()
      const buttons = [...nav.querySelectorAll('.section-page__links button')]
      return {
        width: box.width,
        labelsVisible: getComputedStyle(nav.querySelector('.section-page__links')).display !== 'none',
        labelsFit: buttons.every(button => button.scrollWidth <= button.clientWidth && button.getBoundingClientRect().right <= box.right),
        pageFits: document.documentElement.scrollWidth <= innerWidth,
        selectorWidth: nav.querySelector('select').getBoundingClientRect().width,
      }
    })
    assert.ok(metrics.pageFits, `Page overflow at ${width}px`)
    if (width >= 900) {
      assert.ok(metrics.labelsVisible && metrics.labelsFit, `Navigation labels clipped at ${width}px`)
      assert.ok(metrics.width > normalWidth, `Navigation did not grow at ${width}px`)
    } else {
      assert.equal(metrics.labelsVisible, false)
      assert.ok(Math.abs(metrics.width - normalWidth) <= 1, `Mobile navigation shrank at ${width}px`)
      assert.ok(metrics.selectorWidth > 0)
    }
    await review.capture(`navigation-double-text-${width}`)
    assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `navigation-double-text-${width}.axe.json`), 'utf8')), [])
    review.observations.push({ viewport: width, normalWidth, ...metrics })
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  console.log('Enlarged navigation labels and mobile selector layout passed at seven widths')
} finally {
  await review.flush()
  await review.browser.close()
}
