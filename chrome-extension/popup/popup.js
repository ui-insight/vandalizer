const BRIDGE_ID = 'vandalizer-bridge'
const form = document.getElementById('connect')
const input = document.getElementById('origin')
const status = document.getElementById('status')
const sites = document.getElementById('sites')

function show(text, bad = false) {
  status.textContent = text
  status.className = bad ? 'status bad' : 'status'
}

async function load() {
  const { vandalizerOrigin } = await chrome.storage.local.get('vandalizerOrigin')
  if (vandalizerOrigin) {
    input.value = vandalizerOrigin
    show(`Connected to ${vandalizerOrigin}. Reload any open Vandalizer tab after changing this.`)
  }
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
  show(`Connected to ${origin}. Reload your Vandalizer tab.`)
  await listSites(origin)
})

load()
