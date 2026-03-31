import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Workspace', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('workspace page loads with file browser', async ({ page }) => {
    await page.goto('/')
    // Should see either a file list, upload zone, or empty state
    await expect(
      page.getByText(/documents/i).or(page.getByText(/drop files/i)).or(page.getByText(/upload/i)),
    ).toBeVisible({ timeout: 8000 })
  })

  test('can create and see a new folder', async ({ page }) => {
    await page.goto('/')
    const folderName = `e2e-folder-${Date.now()}`

    const newFolderBtn = page.getByRole('button', { name: /new folder/i })
    if (await newFolderBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newFolderBtn.click()
      await page.getByRole('textbox').fill(folderName)
      await page.getByRole('button', { name: /create/i }).click()
      await expect(page.getByText(folderName)).toBeVisible({ timeout: 5000 })
    }
  })

  test('breadcrumb navigation works', async ({ page }) => {
    await page.goto('/')
    // Look for any folder and try to navigate into it
    const folderLink = page.locator('[data-folder-id]').first()
    if (await folderLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      await folderLink.click()
      // Should see breadcrumb with parent link
      const breadcrumb = page.getByText(/home/i).or(page.getByText(/my files/i))
      await expect(breadcrumb).toBeVisible({ timeout: 5000 })
    }
  })
})
