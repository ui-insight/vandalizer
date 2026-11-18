import workerScript from '../../../chrome-extension/background/service-worker.js?raw'
import { expect, it, vi } from 'vitest'

function worker() {
  const chrome = {
    runtime: { id: 'ours', getURL: (path: string) => `chrome-extension://ours/${path}`, getManifest: () => ({ version: '2.0.0' }), onInstalled: { addListener: vi.fn() }, onStartup: { addListener: vi.fn() }, onMessage: { addListener: vi.fn() }, onMessageExternal: { addListener: vi.fn() } },
    storage: { local: { get: vi.fn(async () => ({ vandalizerOrigin: 'https://vandalizer.example.edu' })) } },
    tabs: { query: vi.fn(async () => [{ id: 42 }]) },
    permissions: { contains: vi.fn(async () => false) },
    scripting: { executeScript: vi.fn(async () => []), getRegisteredContentScripts: vi.fn(async () => []), registerContentScripts: vi.fn() },
  }
  const script = workerScript.replace(/^import .* from .*\n/m, '')
  const state = new Function('chrome', `${script}\nreturn { pendingPermissions, readTab, handleCommand, guardSite };`)(chrome)
  return { chrome, state, receive: chrome.runtime.onMessage.addListener.mock.calls[0][0], external: chrome.runtime.onMessageExternal.addListener.mock.calls[0][0] }
}
it('accepts permission decisions from its exact extension page even when it has a tab', () => {
  const { receive, state } = worker()
  const decide = vi.fn()
  state.pendingPermissions.set('request-1', decide)
  receive({ type: 'vz-permission-decision', id: 'request-1', granted: true }, { id: 'ours', url: 'chrome-extension://ours/permission/permission.html?id=request-1', tab: { id: 12 } }, vi.fn())
  expect(decide).toHaveBeenCalledWith(true)
})
it.each([
  { id: 'ours', url: 'https://evil.example/permission/permission.html?id=request-1' },
  { id: 'other', url: 'chrome-extension://ours/permission/permission.html?id=request-1' },
  { id: 'ours', url: 'chrome-extension://ours/popup/popup.html' },
])('ignores a permission decision from an unrelated sender: %j', sender => {
  const { receive, state } = worker()
  const decide = vi.fn()
  state.pendingPermissions.set('request-1', decide)
  receive({ type: 'vz-permission-decision', id: 'request-1', granted: true }, sender, vi.fn())
  expect(decide).not.toHaveBeenCalled()
})
it('public discovery only reveals presence; it never runs external commands', () => {
  const { external } = worker()
  const respond = vi.fn()
  external({ type: 'vz-installed' }, {}, respond)
  expect(respond).toHaveBeenCalledWith({ installed: true, version: '2.0.0' })
  respond.mockClear()
  external({ type: 'vz-command', tool: 'browser_read' }, {}, respond)
  expect(respond).not.toHaveBeenCalled()
})
it('does not inject a reader after a redirect to a site without permission', async () => {
  const { state, chrome } = worker()
  expect(await state.readTab({ id: 2, url: 'https://unapproved.example/login' }, '')).toMatchObject({ error: 'unapproved_site' })
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
})
it('does not read or act on Vandalizer itself, though that address holds a site permission', async () => {
  const { state, chrome } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  // A link or redirect landed the working tab on the app, admin pages included.
  const landed = { id: 2, url: 'https://vandalizer.example.edu/admin/config' }
  expect(await state.guardSite(landed)).toMatchObject({ error: 'unapproved_site', site: 'vandalizer.example.edu' })
  expect(await state.readTab(landed, '')).toMatchObject({ error: 'unapproved_site' })
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
  // Another site the person allowed is still read.
  expect(await state.guardSite({ id: 2, url: 'https://fin.example.edu/award' })).toBeNull()
})
it("refuses a page outside the administrator's site list, even one the person allowed", async () => {
  const { state, chrome } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1, windowId: 1, index: 0 } }
  const opened = await state.handleCommand({ tool: 'browser_open', args: { url: 'https://bank.example.com/' }, allowedHosts: ['Example.edu'] }, sender)
  expect(opened).toMatchObject({ error: 'site_not_allowed_by_admin', site: 'bank.example.com' })
  // A redirect that leaves the list is not read; a subdomain of a listed domain is.
  expect(await state.readTab({ id: 2, url: 'https://sso.other.org/login' }, '', ['example.edu'])).toMatchObject({ error: 'site_not_allowed_by_admin' })
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
  expect(await state.guardSite({ id: 2, url: 'https://fin.example.edu/award' }, ['example.edu'])).toBeNull()
  expect(await state.guardSite({ id: 2, url: 'https://notexample.edu/' }, ['example.edu'])).toMatchObject({ error: 'site_not_allowed_by_admin' })
})

it('restores only a saved, granted connection after browser startup', async () => {
  const { chrome } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  chrome.runtime.onStartup.addListener.mock.calls[0][0]()
  const { waitFor } = await import('@testing-library/react')
  await waitFor(() => expect(chrome.scripting.executeScript).toHaveBeenCalledWith({ target: { tabId: 42 }, files: ['content/bridge.js'] }))
})
it('does not restore a connection whose permission was removed', async () => {
  const { chrome } = worker()
  chrome.runtime.onInstalled.addListener.mock.calls[0][0]()
  const { waitFor } = await import('@testing-library/react')
  await waitFor(() => expect(chrome.permissions.contains).toHaveBeenCalled())
  expect(chrome.scripting.registerContentScripts).not.toHaveBeenCalled()
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
})

it('announces connection only to the saved app origin while its grant still exists', async () => {
  const { state, chrome } = worker()
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1 } }
  expect(await state.handleCommand({ tool: 'browser_status' }, sender)).toMatchObject({ error: 'browser_not_connected' })
  chrome.permissions.contains.mockResolvedValue(true)
  expect(await state.handleCommand({ tool: 'browser_status' }, sender)).toMatchObject({ ok: true })
  expect(await state.handleCommand({ tool: 'browser_status' }, { ...sender, origin: 'https://unrelated.example' })).toMatchObject({ error: 'not_allowed' })
})
