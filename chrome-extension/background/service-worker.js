// Vandalizer Browser: runs chat's browser tools in a working tab.
//
// The Vandalizer chat page sends each tool call through content/bridge.js.
// Only the Vandalizer address set in the popup may send commands, and only
// sites the person allowed (Chrome's own per-site permission) can be opened
// or read.

import { clickRef, readPage, selectRef, typeRef } from './page-tools.js'

const MAX_PAGE_CHARS = 20000
const LOAD_TIMEOUT_MS = 30000
// Chat's page waits 175s for browser_open (the server 180s): permission
// (120s) plus loading (up to 31s) plus reading fits inside that.
const PERMISSION_TIMEOUT_MS = 120000
const KEEPALIVE_MS = 20000

// Public discovery only. External pages cannot run commands or grant access.
chrome.runtime.onMessageExternal.addListener((msg, _sender, respond) => {
  if (msg?.type === 'vz-installed') respond({ installed: true, version: chrome.runtime.getManifest().version })
})

const pendingPermissions = new Map()

// Chrome clears dynamic registrations on an unpacked-extension reload.
// Restore the saved, already granted connection and repair open app tabs.
async function restoreBridge() {
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  if (!vandalizerOrigin || !(await chrome.permissions.contains({ origins: [`${vandalizerOrigin}/*`] }))) return
  const scripts = await chrome.scripting.getRegisteredContentScripts({ ids: ['vandalizer-bridge'] })
  if (!scripts.length) await chrome.scripting.registerContentScripts([{
    id: 'vandalizer-bridge', matches: [`${vandalizerOrigin}/*`], js: ['content/bridge.js'],
    runAt: 'document_start', persistAcrossSessions: true,
  }])
  for (const tab of await chrome.tabs.query({ url: `${vandalizerOrigin}/*` })) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content/bridge.js'] }).catch(() => {})
  }
}
chrome.runtime.onInstalled.addListener(() => { restoreBridge().catch(console.error) })
chrome.runtime.onStartup.addListener(() => { restoreBridge().catch(console.error) })

// Chrome stops a service worker after 30 seconds without extension API
// calls, even while a command is waiting on the person's click in the
// permission window. That would drop the pending answer, so keep it awake
// while any command is in flight; each API call resets Chrome's clock.
let inFlight = 0
let keepalive = null
function hold() {
  if (inFlight++ === 0) keepalive = setInterval(() => { chrome.runtime.getPlatformInfo().catch(() => {}) }, KEEPALIVE_MS)
}
function release() {
  if (--inFlight === 0) {
    clearInterval(keepalive)
    keepalive = null
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === 'vz-command') {
    hold()
    handleCommand(msg, sender)
      .then(sendResponse, (err) => sendResponse({
        error: 'extension_error',
        message: String(err?.message || err),
      }))
      .finally(release)
    return true
  }
  if (msg?.type === 'vz-permission-decision' && sender.id === chrome.runtime.id
      && sender.url?.startsWith(chrome.runtime.getURL('permission/permission.html?'))) {
    pendingPermissions.get(msg.id)?.(Boolean(msg.granted))
    sendResponse({ ok: true })
    return false
  }
  return false
})

async function handleCommand(msg, sender) {
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  if (!vandalizerOrigin || sender.id !== chrome.runtime.id || sender.origin !== vandalizerOrigin || !sender.tab) {
    return { error: 'not_allowed', message: 'This page is not the Vandalizer address set in the extension.' }
  }
  if (!(await chrome.permissions.contains({ origins: [`${vandalizerOrigin}/*`] }))) {
    return { error: 'browser_not_connected', message: 'Reconnect this Vandalizer site in the extension popup.' }
  }
  if (msg.tool === 'browser_status') return { ok: true, version: chrome.runtime.getManifest().version }
  if (msg.tool === 'browser_focus') return withTab(sender.tab.id, null, async (tab) => {
    await chrome.windows.update(tab.windowId, { focused: true })
    await chrome.tabs.update(tab.id, { active: true })
    return { ok: true }
  })
  if (browserActionPending) return { error: 'browser_busy', message: 'Another browser action is running. Wait for it to finish, then read the working tab again.' }
  browserActionPending = true
  try {
    return await runBrowserAction(msg, sender.tab, vandalizerOrigin)
  } finally {
    browserActionPending = false
  }
}

let browserActionPending = false
async function runBrowserAction(msg, chatTab, vandalizerOrigin) {
  const args = msg.args || {}
  const conversation = typeof msg.conversation === 'string' ? msg.conversation : null
  // The sites the Vandalizer administrator allows, sent with each chat
  // command; empty means no limit beyond what the person allowed.
  const hosts = Array.isArray(msg.allowedHosts)
    ? msg.allowedHosts.filter((h) => typeof h === 'string' && h).map((h) => h.toLowerCase())
    : []
  switch (msg.tool) {
    case 'browser_open': return openUrl(String(args.url || ''), chatTab, vandalizerOrigin, hosts, conversation)
    case 'browser_finish': return changeWorkingTab(() => releaseWorkingTab(chatTab.id, conversation))
    case 'browser_read': return withTab(chatTab.id, conversation, (tab) => readTab(tab, String(args.query || ''), hosts))
    case 'browser_click': return withTab(chatTab.id, conversation, async (tab) => {
      const blocked = await guardSite(tab, hosts)
      if (blocked) return blocked
      const outcome = await runInTab(tab.id, clickRef, [Number(args.ref)])
      if (outcome?.open_url) {
        const target = new URL(outcome.open_url)
        if (target.origin !== new URL(tab.url).origin) {
          if (!adminAllows(target.hostname, hosts)) return notOnAdminList(target.hostname)
          if (target.username || target.password || target.search || target.hash) {
            return { error: 'link_needs_open', site: target.hostname, message: 'The link opens another site and includes parameterized address details. Ask the person to open the requested section in the working tab, then continue.' }
          }
          return { error: 'link_needs_open', url: target.href, site: target.hostname, message: 'Use browser_open with this URL and normal site approval to reuse the working tab.' }
        }
        await chrome.tabs.update(tab.id, { url: target.href })
        await settle(tab.id)
        return { clicked: outcome.clicked, ...(await readTab(await chrome.tabs.get(tab.id), '', hosts)) }
      }
      if (!outcome?.ok) return outcome
      await settle(tab.id)
      return { ...outcome, ...(await readTab(await chrome.tabs.get(tab.id), '', hosts)) }
    })
    case 'browser_type': return withTab(chatTab.id, conversation, async (tab) => {
      const blocked = await guardSite(tab, hosts)
      if (blocked) return blocked
      return runInTab(tab.id, typeRef, [Number(args.ref), String(args.text ?? '')])
    })
    case 'browser_select': return withTab(chatTab.id, conversation, async (tab) => {
      const blocked = await guardSite(tab, hosts)
      if (blocked) return blocked
      const outcome = await runInTab(tab.id, selectRef, [Number(args.ref), String(args.option ?? '')])
      if (!outcome?.ok) return outcome
      // Many older portals reload the page when a drop-down changes.
      await settle(tab.id)
      return { ...outcome, ...(await readTab(await chrome.tabs.get(tab.id), '', hosts)) }
    })
    default:
      return { error: 'unknown_tool', message: `Unknown browser tool ${msg.tool}` }
  }
}

// ── The working tab ────────────────────────────────────────────────────────

// An open from two chat tabs can arrive before either has saved its tab ID.
// Serialize allocation and cleanup, but never hold this queue while waiting
// for permission or a page load.
let tabChanges = Promise.resolve()
function changeWorkingTab(action) {
  const changed = tabChanges.then(action)
  tabChanges = changed.catch(() => {})
  return changed
}
const tabKeys = ['workingTabId', 'workingOwnerTabId', 'workingConversation', 'workingTabInspected']

chrome.tabs.onActivated.addListener(({ tabId }) => {
  void changeWorkingTab(async () => {
    const { workingTabId } = await chrome.storage.session.get('workingTabId')
    if (tabId === workingTabId) await chrome.storage.session.set({ workingTabInspected: true })
  }).catch(console.error)
})

chrome.tabs.onRemoved.addListener((tabId) => {
  void changeWorkingTab(async () => {
    const state = await chrome.storage.session.get(tabKeys)
    if (state.workingTabId === tabId) {
      await chrome.storage.session.remove(tabKeys)
    } else if (state.workingOwnerTabId === tabId) {
      await releaseWorkingTab(tabId, state.workingConversation)
    }
  }).catch(console.error)
})

// Release exactly the page this chat acquired. A completion from a detached
// conversation can arrive after a different conversation opened its source.
async function releaseWorkingTab(ownerId, conversation) {
  const state = await chrome.storage.session.get(tabKeys)
  if (!state.workingTabId || state.workingOwnerTabId !== ownerId || state.workingConversation !== conversation) {
    return { ok: true, working_tab: 'none' }
  }
  const tab = await workingTab()
  const keep = tab && (state.workingTabInspected || tab.active || tab.pinned)
  if (tab && !keep) await chrome.tabs.remove(tab.id)
  await chrome.storage.session.remove(tabKeys)
  return { ok: true, working_tab: !tab ? 'none' : keep ? 'kept' : 'closed' }
}

function openWorkingTab(url, chatTab, conversation = null) {
  return changeWorkingTab(async () => {
    // A site approval can arrive after the requesting chat tab was closed.
    await chrome.tabs.get(chatTab.id)
    const state = await chrome.storage.session.get(tabKeys)
    let tab = await workingTab()
    const sameChat = state.workingOwnerTabId === chatTab.id && state.workingConversation === conversation
    if (tab && (tab.pinned || (!sameChat && (state.workingTabInspected || tab.active)))) tab = null
    if (tab) {
      tab = await chrome.tabs.update(tab.id, { url })
      await chrome.storage.session.set({ workingOwnerTabId: chatTab.id, workingConversation: conversation })
    } else {
      tab = await chrome.tabs.create({ url, active: false, openerTabId: chatTab.id, windowId: chatTab.windowId, index: chatTab.index + 1 })
      await chrome.storage.session.set({ workingTabId: tab.id, workingOwnerTabId: chatTab.id, workingConversation: conversation, workingTabInspected: false })
    }
    return tab
  })
}

async function workingTab() {
  const { workingTabId } = await chrome.storage.session.get('workingTabId')
  if (typeof workingTabId !== 'number') return null
  try { return await chrome.tabs.get(workingTabId) } catch { return null }
}

async function withTab(ownerId, conversation, fn) {
  const { workingOwnerTabId, workingConversation } = await chrome.storage.session.get(tabKeys)
  if ((typeof workingOwnerTabId === 'number' && workingOwnerTabId !== ownerId)
      || (conversation && workingConversation && workingConversation !== conversation)) {
    return { error: 'working_tab_changed', message: 'Another chat opened a different working page. Reopen the requested source in this chat before reading or using its controls.' }
  }
  const tab = await workingTab()
  if (!tab) return { error: 'no_open_page', message: 'No page is open yet. Use browser_open first.' }
  return fn(tab)
}

async function openUrl(raw, chatTab, vandalizerOrigin, hosts = [], conversation = null) {
  let url
  try { url = new URL(raw) } catch { return { error: 'bad_url', message: `Not a web address: ${raw}` } }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return { error: 'bad_url', message: 'Only http and https addresses can be opened.' }
  if (url.origin === vandalizerOrigin) return { error: 'bad_url', message: 'Use Vandalizer tools for Vandalizer itself.' }

  if (!adminAllows(url.hostname, hosts)) return notOnAdminList(url.hostname)

  const pattern = sitePattern(url)
  if (!(await chrome.permissions.contains({ origins: [pattern] }))) {
    const granted = await askForSite(url.hostname, pattern)
    if (!granted) {
      return { error: 'site_not_allowed', site: url.hostname, message: `The person did not allow ${url.hostname}. Ask whether they want to.` }
    }
  }

  const tab = await openWorkingTab(url.href, chatTab, conversation)
  await settle(tab.id)
  return readTab(await chrome.tabs.get(tab.id), '', hosts)
}

// A listed domain covers its subdomains. The server applies the same rule
// (backend/app/services/browser_policy.py) to every page it is sent.
function adminAllows(hostname, hosts) {
  const host = String(hostname || '').toLowerCase()
  return !hosts.length || hosts.some((domain) => host === domain || host.endsWith(`.${domain}`))
}

function notOnAdminList(hostname) {
  return {
    error: 'site_not_allowed_by_admin',
    site: hostname,
    message: `${hostname} is not on the list of sites your Vandalizer administrator allows the browser to use. Nothing was opened or read there.`,
  }
}

function sitePattern(url) {
  return `${url.protocol}//${url.hostname}/*`
}

// A redirect can land the tab on a site that was never allowed, such as a
// single sign-on page. Never read or act there.
async function guardSite(tab, hosts = []) {
  let url
  try { url = new URL(tab.url || '') } catch { url = null }
  // Vandalizer's own address holds a site permission (the bridge runs
  // there), so a link or redirect that lands the tab on it would otherwise
  // pass: chat could then read and click inside Vandalizer as the person.
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  if (url && vandalizerOrigin && url.origin === vandalizerOrigin) {
    return {
      error: 'unapproved_site',
      site: url.hostname,
      message: 'The working tab is now on Vandalizer itself, which the browser tools do not read or act on. Use Vandalizer tools for Vandalizer.',
    }
  }
  if (url && !adminAllows(url.hostname, hosts)) {
    return {
      ...notOnAdminList(url.hostname),
      message: `The working tab is now on ${url.hostname}, which is not on the list of sites your Vandalizer administrator allows, so it was not read. If it is a sign-in page, ask the person to sign in in that tab and tell you when they are done. Do not ask for their password.`,
    }
  }
  if (url && (url.protocol === 'https:' || url.protocol === 'http:')
      && await chrome.permissions.contains({ origins: [sitePattern(url)] })) return null
  return {
    error: 'unapproved_site',
    site: url?.hostname || '',
    message: `The working tab is now on ${url?.hostname || 'a page'} that the person has not allowed. If it is a sign-in page, ask them to sign in in that tab and tell you when they are done. Do not ask for their password.`,
  }
}

async function readTab(tab, query, hosts = []) {
  const blocked = await guardSite(tab, hosts)
  if (blocked) return blocked
  const page = await runInTab(tab.id, readPage, [query, MAX_PAGE_CHARS])
  if (!page || page.error) return page || { error: 'read_failed' }
  if (page.pdf_viewer) return {
    error: 'pdf_viewer', site: new URL(tab.url).hostname,
    message: 'Chrome opened a PDF viewer. Its document text is unavailable to the browser tool. Ask the person to attach the PDF, then read the attachment with document tools.',
  }
  return {
    page,
    ...(page.login_required ? {
      login_required: true,
      message: 'This page has a password field. If it is a sign-in page, ask the person to sign in in the working browser tab and tell you when they are done; otherwise carry on. Never type a password.',
    } : {}),
  }
}

async function runInTab(tabId, func, args) {
  try {
    const [injection] = await chrome.scripting.executeScript({ target: { tabId }, func, args })
    return injection?.result
  } catch (err) {
    return { error: 'page_unavailable', message: String(err?.message || err) }
  }
}

async function settle(tabId) {
  const started = Date.now()
  await delay(400)
  while (Date.now() - started < LOAD_TIMEOUT_MS) {
    let tab
    try { tab = await chrome.tabs.get(tabId) } catch { return }
    if (tab.status === 'complete') break
    await delay(250)
  }
  // Let script-built pages fill in after the load event.
  await delay(700)
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ── Asking for a site ──────────────────────────────────────────────────────
// Chrome only grants a site from a click in an extension page, so open a
// small window with Allow and Don't allow.

async function askForSite(host, pattern) {
  const id = crypto.randomUUID()
  const params = new URLSearchParams({ id, host, pattern })
  const win = await chrome.windows.create({
    url: chrome.runtime.getURL(`permission/permission.html?${params}`),
    type: 'popup', width: 460, height: 480, focused: true,
  })
  return new Promise((resolve) => {
    let done = false
    const finish = async (clicked) => {
      if (done) return
      done = true
      clearTimeout(timer)
      chrome.windows.onRemoved.removeListener(onRemoved)
      pendingPermissions.delete(id)
      resolve(clicked && await chrome.permissions.contains({ origins: [pattern] }))
    }
    const timer = setTimeout(() => {
      finish(false)
      chrome.windows.remove(win.id).catch(() => {})
    }, PERMISSION_TIMEOUT_MS)
    const onRemoved = (windowId) => { if (windowId === win.id) finish(false) }
    chrome.windows.onRemoved.addListener(onRemoved)
    pendingPermissions.set(id, finish)
  })
}
