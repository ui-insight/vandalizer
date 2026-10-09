import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createReview } from './harness.mjs'

const legacy = process.env.REVIEW_LEGACY_NOTICE === '1'
const fixtures = process.env.REVIEW_NOTICE_FIXTURES
  ? pathToFileURL(resolve(process.env.REVIEW_NOTICE_FIXTURES) + '/')
  : new URL('../../../artifacts/visual-review/certification-completion-notices-2026-10-07/', import.meta.url)
const labels = legacy ? ['legacy', 'legacy-long'] : ['single', 'full', 'long']
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: `Rendered ${legacy ? 'legacy' : 'credential-specific'} email fixtures only. No email provider, delivery, live learner or credit operation. Email-client compatibility remains separate.` })
const { page, context } = review
page.setDefaultTimeout(15000)
await context.route('**/__qa/certification-notice/*', async route => {
  const label = new URL(route.request().url()).pathname.split('/').at(-1)
  assert.ok(labels.includes(label))
  await route.fulfill({ contentType: 'text/html', body: await readFile(new URL(label + '.html', fixtures), 'utf8') })
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    for (const label of labels) {
      await page.goto(review.baseURL + '/__qa/certification-notice/' + label)
      if (native) await review.setBrowserZoom(2)
      await page.getByRole('heading', { name: legacy ? /^Certified\. Nice work,/ : 'Certification earned' }).waitFor()
      const link = page.getByRole('link', { name: legacy ? 'View Your Certification' : 'View your earned certificates', exact: true })
      assert.equal(await link.getAttribute('href'), review.baseURL + '/certification')
      await link.focus()
      await link.scrollIntoViewIfNeeded()
      const id = `${label}-${width}`
      await review.capture(id)
      const capture = review.captures.at(-1)
      assert.equal(capture.pageWidth, capture.viewport.width)
      assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
      assert.equal(await page.getByText(/1,600|every workflow you publish/).count(), 0)
      if (native) assert.equal(capture.viewport.width, 390)
    }
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ legacyCopy: legacy, credentialBoundCopy: !legacy, originalIssueDate: !legacy, responsiveRenderedEmail: true,
    externalMessages: 0, emailClientCompatibilityVerified: false })
} catch (error) {
  await review.capture('blocked', String(error)); throw error
} finally { await review.flush(); await review.browser.close() }
