import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { items as fixtures } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
const longName = 'Review supporting evidence and budget assumptions for the international research funding application'
let items, folders, failItems, failFolders, failCreate, failRename, failAction, failDelete, writes, creates, renames, moves, deletes
await page.route('**/api/library/library-1/items*', route => {
  const query = new URL(route.request().url()).searchParams
  return failItems ? route.fulfill({ status: 503, json: { detail: 'Library items temporarily unavailable.' } }) : route.fulfill({ json: items.filter(item => (!query.get('search') || item.name.toLowerCase().includes(query.get('search').toLowerCase())) && (!query.get('folder') || item.folder === query.get('folder'))) })
})
await page.route('**/api/library/folders?*', route => failFolders ? route.fulfill({ status: 503, json: { detail: 'Folder list temporarily unavailable.' } }) : route.fulfill({ json: folders }))
await page.route('**/api/library/folders', route => {
  const body = route.request().postDataJSON(); creates.push(body)
  if (failCreate) return route.fulfill({ status: 503, json: { detail: 'Folder could not be created.' } })
  const folder = { uuid: 'created-folder', name: body.name, scope: body.scope, parent_id: null, item_count: 0 }; folders.push(folder)
  return route.fulfill({ json: folder })
})
await page.route('**/api/library/folders/created-folder', route => {
  if (route.request().method() === 'DELETE') {
    deletes.push('created-folder')
    if (failDelete) return route.fulfill({ status: 503, json: { detail: 'Folder could not be deleted.' } })
    folders = folders.filter(folder => folder.uuid !== 'created-folder')
    items = items.map(item => item.folder === 'created-folder' ? { ...item, folder: null } : item)
    return route.fulfill({ json: { ok: true } })
  }
  const body = route.request().postDataJSON(); renames.push(body)
  if (failRename) return route.fulfill({ status: 503, json: { detail: 'Folder name could not be saved.' } })
  folders = folders.map(folder => folder.uuid === 'created-folder' ? { ...folder, ...body } : folder)
  return route.fulfill({ json: folders.find(folder => folder.uuid === 'created-folder') })
})
await page.route('**/api/library/items/*', route => {
  const id = route.request().url().split('/').pop(), body = route.request().postDataJSON(); writes.push({ id, body })
  if (failAction) return route.fulfill({ status: 503, json: { detail: 'Item could not be updated.' } })
  items = items.map(item => item.id === id ? { ...item, ...body } : item)
  return route.fulfill({ json: items.find(item => item.id === id) })
})
await page.route('**/api/library/items/*/touch', route => route.fulfill({ json: { ok: true } }))
await page.route('**/api/library/folders/move-items', route => {
  const body = route.request().postDataJSON(); moves.push(body)
  if (failAction) return route.fulfill({ status: 503, json: { detail: 'Item could not be moved.' } })
  items = items.map(item => body.item_ids.includes(item.id) ? { ...item, folder: body.folder_uuid } : item)
  return route.fulfill({ json: { ok: true } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function views() {
  const toggle = page.locator('.library-views-toggle')
  if (await toggle.isVisible() && await toggle.getAttribute('aria-expanded') === 'false') await toggle.click()
}
async function hideViews() {
  const toggle = page.locator('.library-views-toggle')
  if (await toggle.isVisible() && await toggle.getAttribute('aria-expanded') === 'true') await toggle.click()
}
async function open(width) {
  await page.goto(review.baseURL + '/?mode=files')
  await page.getByRole('navigation', { name: 'Workspace navigation' }).waitFor()
  if (width < 768) await page.getByRole('button', { name: 'Open Library panel', exact: true }).click()
  else await page.getByRole('button', { name:/^(?:Open )?Library(?: panel)?$/ }).click()
  await page.getByRole('textbox', { name: 'Search library' }).waitFor()
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    items = fixtures.map(item => ({ ...item, pinned: false, favorited: false })); items.push({ ...items[0], id: 'folder-item', name: longName, folder: 'evidence' })
    folders = [{ uuid: 'evidence', name: 'Evidence', scope: 'personal', parent_id: null, item_count: 1 }]
    failItems = true; failFolders = true; failCreate = true; failRename = true; failAction = true; failDelete = true; writes = []; creates = []; renames = []; moves = []; deletes = []
    await page.setViewportSize({ width, height }); await open(width)
    await page.getByRole('button', { name: 'Retry items' }).waitFor(); await shot('library-items-error-' + width)
    failItems = false; await page.getByRole('button', { name: 'Retry items' }).click()
    await page.getByRole('button', { name: 'Open ' + fixtures[0].name, exact: true }).waitFor()
    await views(); await page.getByRole('button', { name: 'Retry folders' }).scrollIntoViewIfNeeded(); await shot('library-folders-error-' + width)
    failFolders = false; await page.getByRole('button', { name: 'Retry folders' }).click()
    await page.getByRole('button', { name: 'Open folder Evidence', exact: true }).waitFor()
    await hideViews()
    const search = page.getByRole('textbox', { name: 'Search library' })
    await search.fill('  international  ')
    await page.getByRole('button', { name: 'Open ' + longName, exact: true }).waitFor()
    await shot('library-search-folder-match-' + width)
    await search.fill('no matching library work'); await page.getByRole('heading', { name: 'No items match these filters' }).waitFor()
    await shot('library-no-results-' + width)
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    const row = page.locator('.library-item-row').filter({ has: page.getByRole('button', { name: 'Open ' + fixtures[0].name, exact: true }) })
    await row.hover(); await row.getByRole('button', { name: 'Favorite (shows in all views)', exact: true }).click()
    await page.getByRole('button', { name: 'Retry item action' }).waitFor(); await shot('library-favorite-error-' + width)
    assert.deepEqual(writes, [{ id: 'item-0', body: { favorited: true } }])
    failAction = false; await page.getByRole('button', { name: 'Retry item action' }).click()
    await row.getByRole('button', { name: 'Unfavorite', exact: true }).waitFor()
    assert.deepEqual(writes[1], writes[0]); await shot('library-favorite-saved-' + width)
    await row.hover(); await row.getByRole('button', { name: 'Pin (shows in all views)', exact: true }).click()
    await row.getByRole('button', { name: 'Unpin', exact: true }).waitFor()
    await page.getByRole('combobox', { name: 'Sort library items' }).selectOption('az')
    assert.equal(await page.locator('.library-item-row').first().getByRole('button', { name: /^Open / }).innerText(), fixtures[1].name)
    await views(); await page.getByRole('button', { name: /^Pinned\b/ }).click()
    await row.waitFor(); assert.equal(await page.locator('.library-item-row').count(), 1)
    await shot('library-pinned-view-' + width)
    await views(); await page.getByRole('button', { name: /^All Items\b/ }).click()
    await views(); await page.getByRole('button', { name: 'New folder', exact: true }).click()
    const folderName = page.getByRole('textbox', { name: 'New Library folder name' })
    await folderName.fill('Review drafts'); await folderName.press('Enter')
    await page.getByText('Folder could not be created.', { exact: true }).waitFor()
    assert.equal(await folderName.inputValue(), 'Review drafts'); await folderName.scrollIntoViewIfNeeded(); await shot('library-folder-create-error-' + width)
    failCreate = false; await page.getByRole('button', { name: 'Create folder', exact: true }).click()
    await page.getByRole('button', { name: 'Open folder Review drafts' }).waitFor()
    assert.deepEqual(creates[1], creates[0])
    await page.getByRole('button', { name: 'Folder actions: Review drafts', exact: true }).click()
    await page.getByRole('button', { name: 'Rename', exact: true }).click()
    const rename = page.getByRole('textbox', { name: 'Rename Library folder' })
    await rename.fill('Approved evidence'); await rename.press('Enter')
    await page.getByText('Folder name could not be saved.', { exact: true }).waitFor()
    await rename.scrollIntoViewIfNeeded(); await shot('library-folder-rename-error-' + width)
    failRename = false; await page.getByRole('button', { name: 'Save folder name' }).click()
    await page.getByRole('button', { name: 'Open folder Approved evidence' }).waitFor()
    assert.deepEqual(renames, [{ name: 'Approved evidence' }, { name: 'Approved evidence' }])
    await page.getByRole('button', { name: 'Open folder Approved evidence' }).click()
    await page.getByRole('heading', { name: 'This folder is empty' }).waitFor(); await shot('library-empty-folder-' + width)
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    await row.hover(); await row.getByRole('button', { name: 'More actions' }).click()
    const move = page.getByRole('button', { name: 'Move to folder', exact: true })
    await move.focus(); await move.press('Enter')
    const destination = page.getByRole('button', { name: 'Approved evidence', exact: true }); await destination.focus()
    await shot('library-keyboard-folder-menu-' + width)
    failAction = true; await destination.press('Enter')
    await page.getByRole('button', { name: 'Retry item action' }).waitFor(); await shot('library-move-error-' + width)
    failAction = false; await page.getByRole('button', { name: 'Retry item action' }).click()
    await row.waitFor({ state: 'detached' })
    assert.deepEqual(moves, Array(2).fill({ item_ids: ['item-0'], folder_uuid: 'created-folder' }))
    await views(); await page.getByRole('button', { name: 'Open folder Approved evidence' }).click()
    await row.waitFor(); await shot('library-moved-item-' + width)
    await views(); await page.getByRole('button', { name: 'Folder actions: Approved evidence', exact: true }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await page.getByRole('dialog', { name: 'Delete folder?' }).getByRole('button', { name: 'Delete', exact: true }).click()
    await page.getByText('Folder could not be deleted.', { exact: true }).waitFor()
    await page.getByText('Folder could not be deleted.', { exact: true }).scrollIntoViewIfNeeded()
    await shot('library-folder-delete-error-' + width)
    assert.deepEqual(deletes, ['created-folder'])
    failDelete = false; await page.getByRole('button', { name: 'Folder actions: Approved evidence', exact: true }).click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await page.getByRole('dialog', { name: 'Delete folder?' }).getByRole('button', { name: 'Delete', exact: true }).click()
    await page.getByRole('button', { name: 'Open folder Approved evidence' }).waitFor({ state: 'detached' })
    await hideViews(); await row.waitFor()
    assert.equal(items.find(item => item.id === 'item-0').folder, null)
    assert.deepEqual(deletes, ['created-folder', 'created-folder'])
    await shot('library-folder-delete-restores-items-' + width)
    // A populated list stays browsable and long mixed items remain readable.
    items = Array.from({ length: 120 }, (_, index) => ({ ...fixtures[index % 3], id: 'large-' + index, name: String(index).padStart(3, '0') + ' ' + fixtures[index % 3].name, folder: null }))
    await open(width)
    await page.getByRole('button', { name: 'Open 119 ' + fixtures[2].name, exact: true }).scrollIntoViewIfNeeded()
    await shot('library-large-list-' + width)
    items = []; await open(width)
    await page.getByRole('heading', { name: 'Your library is ready for its first tool' }).waitFor(); await shot('library-empty-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('library-recovery-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
