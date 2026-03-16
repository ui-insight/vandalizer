import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('File upload', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('upload zone is visible in the file browser', async ({ page }) => {
    await expect(
      page.getByRole('region', { name: /upload/i }).or(page.locator('[data-testid="upload-zone"]')),
    ).toBeVisible({ timeout: 5000 })
  })

  test('uploaded PDF appears in the file list', async ({ page }) => {
    // Create a minimal PDF buffer and upload via the API directly
    const pdfContent = Buffer.from(
      '%PDF-1.4\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n' +
        '2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n' +
        '3 0 obj<</Type /Page /MediaBox [0 0 612 792] /Parent 2 0 R>>endobj\n' +
        'xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4 /Root 1 0 R>>\nstartxref\n0\n%%EOF',
    )
    const base64 = pdfContent.toString('base64')

    const response = await page.request.post('/api/files/upload', {
      data: {
        contentAsBase64String: base64,
        fileName: 'e2e-test.pdf',
        extension: 'pdf',
        space: 'personal',
        folder: null,
      },
    })
    expect(response.ok()).toBeTruthy()

    // Reload and check the file appears
    await page.reload()
    await expect(page.getByText('e2e-test.pdf')).toBeVisible({ timeout: 10000 })
  })
})

test.describe('File browser navigation', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('can create and see a new folder', async ({ page }) => {
    const folderName = `e2e-folder-${Date.now()}`

    // Look for "New Folder" button
    const newFolderBtn = page.getByRole('button', { name: /new folder/i })
    if (await newFolderBtn.isVisible()) {
      await newFolderBtn.click()
      await page.getByRole('textbox').fill(folderName)
      await page.getByRole('button', { name: /create/i }).click()
      await expect(page.getByText(folderName)).toBeVisible({ timeout: 5000 })
    }
  })
})
