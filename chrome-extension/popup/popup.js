const BRIDGE_ID = 'vandalizer-bridge'
const form = document.getElementById('connect')
const input = document.getElementById('origin')
const status = document.getElementById('status')
const sites = document.getElementById('sites')
const setupOrigin = new URLSearchParams(location.search).get('origin')
const connectionPage = document.body.dataset.page === 'connect'
let connectedOrigin = ''
let workingTabId

function show(text, bad = false) {
  status.textContent = text
  status.className = bad ? 'status bad' : 'status'
}

function renderConnection(origin, connected) {
  connectedOrigin = connected ? origin : ''
  const ready = connected && (!connectionPage || origin === input.value)
  const panel = document.getElementById('connection')
  panel.hidden = connectionPage && !ready
  panel.dataset.connected = String(ready)
  document.getElementById('connection-label').textContent = ready ? 'Connected' : origin ? 'Connection needs attention' : 'Not connected yet'
  document.getElementById('connection-site').textContent = origin || ''
  document.getElementById('connection-description').textContent = ready ? 'Ready to use with Skills in your Library.' : origin ? 'Site access was removed. Reconnect from your Vandalizer tab.' : 'Connect once to bring your websites into chat.'
  document.getElementById('connected-actions').hidden = !ready
  if (connectionPage) {
    form.hidden = ready
    document.getElementById('page-title').textContent = ready ? 'Your browser is ready' : 'Connect your browser'
    document.getElementById('page-description').textContent = ready ? 'Return to Vandalizer to try a Skill. Each website still needs your permission.' : 'Allow this Vandalizer site to work with your browser. You’ll choose which websites chat may read separately.'
  } else {
    const change = document.getElementById('change-connection')
    change.open = !ready
    change.hidden = ready && (!input.value || input.value === origin)
    document.getElementById('connection-toggle').textContent = ready ? 'Connect a different Vandalizer site' : 'Connect Vandalizer'
    document.getElementById('connection-toggle').hidden = !ready
  }
}

async function focusTab(tab) {
  await chrome.tabs.update(tab.id, { active: true })
  await chrome.windows.update(tab.windowId, { focused: true })
}

document.getElementById('open-vandalizer').addEventListener('click', async () => {
  if (!connectedOrigin) return
  try {
    const tabs = await chrome.tabs.query({ url: `${connectedOrigin}/*` })
    if (tabs.length) await focusTab(tabs[0])
    else await chrome.tabs.create({ url: `${connectedOrigin}/assistant#browser-setup` })
    if (!connectionPage) window.close()
  } catch { show('Could not open Vandalizer. Select your Vandalizer tab and try again.', true) }
})

document.getElementById('open-working')?.addEventListener('click', async () => {
  try { await focusTab(await chrome.tabs.get(workingTabId)); window.close() }
  catch { show('The working tab has closed. Ask chat to open the site again.', true) }
})

async function load() {
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  try {
    const url = new URL(connectionPage ? setupOrigin : tab?.url)
    if (url.protocol === 'https:' || (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) input.value = url.origin
  } catch { /* A Chrome settings page cannot be connected. */ }
  document.querySelector('button[type="submit"]').disabled = !input.value
  const connected = vandalizerOrigin && await chrome.permissions.contains({ origins: [`${vandalizerOrigin}/*`] })
  if (!input.value && (connectionPage || !connected)) show(connectionPage ? 'No valid Vandalizer address. Return to your Vandalizer tab and choose Connect this site in the extension menu.' : 'Open your Vandalizer tab, then reopen this menu to connect.')
  renderConnection(vandalizerOrigin, Boolean(connected))
  if (connected && !connectionPage) {
    const session = await chrome.storage.session.get('workingTabId')
    workingTabId = session.workingTabId
    if (typeof workingTabId === 'number') {
      try { await chrome.tabs.get(workingTabId); document.getElementById('open-working').hidden = false } catch { /* Tab closed. */ }
    }
  }
  await listSites(vandalizerOrigin)
}

async function listSites(vandalizerOrigin) {
  if (!sites) return
  const { origins = [] } = await chrome.permissions.getAll()
  const allowed = origins.filter((o) => !vandalizerOrigin || o !== `${vandalizerOrigin}/*`)
  sites.replaceChildren()
  if (!allowed.length) {
    const li = document.createElement('li')
    li.className = 'empty'
    li.textContent = 'None yet. Chat asks the first time it opens a site.'
    sites.append(li)
    return
  }
  for (const origin of allowed) {
    const li = document.createElement('li')
    const name = document.createElement('span')
    name.textContent = origin.replace(/^https?:\/\//, '').replace(/\/\*$/, '')
    const remove = document.createElement('button')
    remove.type = 'button'
    remove.textContent = 'Remove'
    remove.setAttribute('aria-label', `Remove access to ${name.textContent}`)
    remove.addEventListener('click', async () => {
      try {
        await chrome.permissions.remove({ origins: [origin] })
        await listSites(vandalizerOrigin)
        show(`Access removed for ${name.textContent}. Chat will ask again next time.`)
      } catch { show('Could not remove access. Try again.', true) }
    })
    li.append(name, remove)
    sites.append(li)
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  try {
    let origin
    try {
      const url = new URL(input.value.trim())
      if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
        show('Use an https address (http only for localhost).', true)
        return
      }
      origin = url.origin
    } catch {
      show('That is not a web address.', true)
      return
    }
    if (!connectionPage) {
      // Chrome closes action popups when it shows a permissions prompt. Keep
      // the grant and registration in a full extension page that stays alive.
      await chrome.tabs.create({ url: chrome.runtime.getURL(`popup/connect.html?origin=${encodeURIComponent(origin)}`) })
      window.close()
      return
    }
    // Must run straight from the click: Chrome only grants a site from a gesture.
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
    if (!granted) {
      show('Chrome did not allow the extension on that address.', true)
      return
    }
    const { vandalizerOrigin: previous } = await chrome.storage.local.get('vandalizerOrigin')
    const registered = await chrome.scripting.getRegisteredContentScripts({ ids: [BRIDGE_ID] })
    if (registered.length) await chrome.scripting.unregisterContentScripts({ ids: [BRIDGE_ID] })
    await chrome.scripting.registerContentScripts([{
      id: BRIDGE_ID,
      matches: [`${origin}/*`],
      js: ['content/bridge.js'],
      runAt: 'document_start',
      persistAcrossSessions: true,
    }])
    if (previous && previous !== origin) await chrome.permissions.remove({ origins: [`${previous}/*`] }).catch(() => {})
    await chrome.storage.local.set({ vandalizerOrigin: origin })
    // Register for future loads, then attach to already open tabs immediately.
    const tabs = await chrome.tabs.query({ url: `${origin}/*` })
    let failed = false
    for (const tab of tabs) {
      try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content/bridge.js'] }) }
      catch { failed = true }
    }
    renderConnection(origin, true)
    show(failed ? 'Reload your Vandalizer tab to finish connecting.' : 'No reload needed. Your open Vandalizer tabs are connected.')
    await listSites(origin)
  } catch (err) { show(`Could not connect. ${err?.message || 'Return to Vandalizer and try again.'}`, true) }
})

load().catch(() => show('Could not check the connection. Close this menu and try again.', true))
