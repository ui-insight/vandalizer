import workerScript from '../../../chrome-extension/background/service-worker.js?raw'
import { expect, it, vi } from 'vitest'

function worker() {
  const session: Record<string, unknown> = {}
  const tab = { id: 91, active: false, pinned: false, url: 'https://portal.example.edu' }
  const chrome = {
    runtime: { id: 'ours', getURL: (path: string) => `chrome-extension://ours/${path}`, getManifest: () => ({ version: '2.0.0' }), onInstalled: { addListener: vi.fn() }, onStartup: { addListener: vi.fn() }, onMessage: { addListener: vi.fn() }, onMessageExternal: { addListener: vi.fn() } },
    storage: { local: { get: vi.fn(async () => ({ vandalizerOrigin: 'https://vandalizer.example.edu' })) }, session: {
      get: vi.fn(async () => ({ ...session })),
      set: vi.fn(async (values: Record<string, unknown>) => { Object.assign(session, values) }),
      remove: vi.fn(async (keys: string[]) => { keys.forEach(key => delete session[key]) }),
    } },
    tabs: { query: vi.fn(async () => [{ id: 42 }]), get: vi.fn(async () => tab), create: vi.fn(async () => tab),
      update: vi.fn(async () => tab), remove: vi.fn(), onActivated: { addListener: vi.fn() }, onRemoved: { addListener: vi.fn() } },
    permissions: { contains: vi.fn(async () => false) },
    scripting: { executeScript: vi.fn(async () => []), getRegisteredContentScripts: vi.fn(async () => []), registerContentScripts: vi.fn() },
  }
  const script = workerScript.replace(/^import .* from .*\n/m, '')
  const state = new Function('chrome', 'readPage', 'clickRef', `${script}\nreturn { pendingPermissions, readTab, handleCommand, guardSite, openWorkingTab, tabIdle: () => tabChanges };`)(chrome, () => {}, () => {})
  return { chrome, state, session, tab, receive: chrome.runtime.onMessage.addListener.mock.calls[0][0], external: chrome.runtime.onMessageExternal.addListener.mock.calls[0][0] }
}

it('uses one working tab across opens and closes it only with the last owning chat', async () => {
  const { chrome, state, session } = worker()
  await Promise.all([1, 2].map(id => state.openWorkingTab('https://portal.example.edu', { id, windowId: 3, index: 1 })))
  expect(chrome.tabs.create).toHaveBeenCalledTimes(1)
  expect(session.workingOwnerTabId).toBe(2)
  const removed = chrome.tabs.onRemoved.addListener.mock.calls[0][0]
  removed(1)
  await state.tabIdle()
  expect(chrome.tabs.remove).not.toHaveBeenCalled()
  removed(2)
  await state.tabIdle()
  expect(chrome.tabs.remove).toHaveBeenCalledWith(91)
  expect(session.workingTabId).toBeUndefined()
})

it.each(['inspected', 'pinned'])('leaves the %s working tab with its user', async mode => {
  const { chrome, state, session, tab } = worker()
  await state.openWorkingTab(tab.url, { id: 1, windowId: 3, index: 1 })
  if (mode === 'inspected') chrome.tabs.onActivated.addListener.mock.calls[0][0]({ tabId: tab.id })
  else tab.pinned = true
  chrome.tabs.onRemoved.addListener.mock.calls[0][0](1)
  await state.tabIdle()
  expect(chrome.tabs.remove).not.toHaveBeenCalled()
  expect(session.workingTabId).toBeUndefined()
})

it('does not read the source opened by another chat', async () => {
  const { chrome, state, tab } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  await state.openWorkingTab(tab.url, { id: 1, windowId: 3, index: 1 })
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 2 } }
  expect(await state.handleCommand({ tool: 'browser_read' }, sender)).toMatchObject({ error: 'working_tab_changed' })
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
})
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

it('releases an unattended page at task completion and ignores stale releases from the same chat tab', async () => {
  const { chrome, state, tab } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1, windowId: 3, index: 1 } }
  await state.openWorkingTab(tab.url, sender.tab, 'new-chat')
  expect(await state.handleCommand({ tool: 'browser_finish', conversation: 'old-chat' }, sender)).toEqual({ ok: true, working_tab: 'none' })
  expect(await state.handleCommand({ tool: 'browser_read', conversation: 'old-chat' }, sender)).toMatchObject({ error: 'working_tab_changed' })
  expect(chrome.tabs.remove).not.toHaveBeenCalled()
  expect(await state.handleCommand({ tool: 'browser_finish', conversation: 'new-chat' }, sender)).toEqual({ ok: true, working_tab: 'closed' })
  expect(await state.handleCommand({ tool: 'browser_finish', conversation: 'new-chat' }, sender)).toEqual({ ok: true, working_tab: 'none' })
  expect(chrome.tabs.remove.mock.calls).toEqual([[91]])
})

it('leaves an inspected page open on task completion', async () => {
  const { chrome, state, session, tab } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1 } }
  await state.openWorkingTab(tab.url, sender.tab, 'research')
  chrome.tabs.onActivated.addListener.mock.calls[0][0]({ tabId: tab.id })
  expect(await state.handleCommand({ tool: 'browser_finish', conversation: 'research' }, sender)).toEqual({ ok: true, working_tab: 'kept' })
  expect(chrome.tabs.remove).not.toHaveBeenCalled()
  expect(session.workingTabId).toBeUndefined()
})

it.each([
  ['https://outside.example/records', ['example.edu'], 'site_not_allowed_by_admin'],
  ['https://outside.example/records', [], 'link_needs_open'],
  ['https://outside.example/records?private=123', [], 'link_needs_open'],
])('checks the site before following a new-context link to %s', async (url, allowedHosts, error) => {
  const { chrome, state, tab } = worker()
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1 } }
  await state.openWorkingTab(tab.url, sender.tab)
  chrome.permissions.contains.mockResolvedValue(true)
  chrome.scripting.executeScript.mockResolvedValueOnce([{ result: { open_url: url } }] as never[])
  const result = await state.handleCommand({ tool: 'browser_click', args: { ref: 1 }, allowedHosts }, sender)
  expect(result.error).toBe(error)
  if (String(url).includes('?') || error === 'site_not_allowed_by_admin') expect(result.url).toBeUndefined()
  else expect(result.url).toBe(url)
  expect(chrome.tabs.update).not.toHaveBeenCalled()
  expect(chrome.tabs.create).toHaveBeenCalledTimes(1)
})

it('navigates and reads a same-site new-context link in the existing tab', async () => {
  const { chrome, state, tab } = worker()
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1 } }
  await state.openWorkingTab(tab.url, sender.tab)
  const destination = tab.url + '/record'
  chrome.permissions.contains.mockResolvedValue(true)
  chrome.scripting.executeScript.mockResolvedValueOnce([{ result: { open_url: destination, clicked: 'Record' } }] as never[])
    .mockResolvedValueOnce([{ result: { url: destination, title: 'Record' } }] as never[])
  Object.assign(tab, { status: 'complete' })
  const result = await state.handleCommand({ tool: 'browser_click', args: { ref: 1 } }, sender)
  expect(result.page.url).toBe(destination)
  expect(chrome.tabs.update).toHaveBeenCalledWith(tab.id, { url: destination })
  expect(chrome.tabs.create).toHaveBeenCalledTimes(1)
})

it('cleans up a background tab Chrome automatically selects when its opener closes', async () => {
  const { chrome, state, tab } = worker()
  await state.openWorkingTab(tab.url, { id: 1, windowId: 3, index: 1 })
  tab.active = true
  chrome.tabs.get.mockRejectedValueOnce(new Error('No tab with id 1'))
  chrome.tabs.onActivated.addListener.mock.calls[0][0]({ tabId: tab.id })
  chrome.tabs.onRemoved.addListener.mock.calls[0][0](1)
  await state.tabIdle()
  expect(chrome.tabs.remove.mock.calls).toEqual([[tab.id]])
})

it('preserves a foreground page when research finishes with its owner still open', async () => {
  const { chrome, state, tab } = worker()
  chrome.permissions.contains.mockResolvedValue(true)
  const sender = { id: 'ours', origin: 'https://vandalizer.example.edu', tab: { id: 1 } }
  await state.openWorkingTab(tab.url, sender.tab, 'research')
  tab.active = true
  expect(await state.handleCommand({ tool: 'browser_finish', conversation: 'research' }, sender)).toEqual({ ok: true, working_tab: 'kept' })
  expect(chrome.tabs.remove).not.toHaveBeenCalled()
})
