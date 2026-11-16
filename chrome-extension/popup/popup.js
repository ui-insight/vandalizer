const BRIDGE_ID = 'vandalizer-bridge'
const form = document.getElementById('connect')
const input = document.getElementById('origin')
const status = document.getElementById('status')
const sites = document.getElementById('sites')
const setupOrigin = new URLSearchParams(location.search).get('origin')

function show(text, bad = false) {
  status.textContent = text
  status.className = bad ? 'status bad' : 'status'
}

async function load() {
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  try {
    const url = new URL(setupOrigin || tab?.url)
    if (url.protocol === 'https:' || (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) input.value = url.origin
  } catch { /* A Chrome settings page cannot be connected. */ }
  document.querySelector('button[type="submit"]').disabled = !input.value
  if (setupOrigin) {
    document.querySelector('h1').textContent = 'Connect Vandalizer Browser'
    document.getElementById('connect-help').textContent = 'Check the Vandalizer address above, then allow the connection. Chrome may show its own site access prompt. Return to your Vandalizer tab when connected.'
    document.querySelector('button[type="submit"]').textContent = 'Allow connection'
  }
  const connected = vandalizerOrigin && await chrome.permissions.contains({ origins: [`${vandalizerOrigin}/*`] })
  show(connected ? `Connected Vandalizer site: ${vandalizerOrigin}` : vandalizerOrigin ? `Access removed for ${vandalizerOrigin}. Reconnect from your Vandalizer tab.` : 'No Vandalizer site connected yet.')
  await listSites(vandalizerOrigin)
}

async function listSites(vandalizerOrigin) {
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
    remove.addEventListener('click', async () => {
      await chrome.permissions.remove({ origins: [origin] })
      await listSites(vandalizerOrigin)
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
    if (!setupOrigin) {
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
    show(`Connected to ${origin}. ${failed ? 'Reload your Vandalizer tab to finish connecting.' : 'Return to Vandalizer. No reload needed.'}`)
    await listSites(origin)
  } catch (err) { show(`Could not connect. ${err?.message || 'Return to Vandalizer and try again.'}`, true) }
})

load()
