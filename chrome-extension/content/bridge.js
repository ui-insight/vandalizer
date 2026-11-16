// Runs only on the Vandalizer address set in the popup. Passes chat's browser
// tool calls from the page to the extension and the answers back.
(() => {
  const PAGE = 'vandalizer-page'
  const EXT = 'vandalizer-extension'
  const announce = () => window.postMessage({ source: EXT, type: 'ready', version: chrome.runtime.getManifest().version }, location.origin)

  window.addEventListener('message', (event) => {
    if (event.source !== window || event.origin !== location.origin) return
    const msg = event.data
    if (!msg || msg.source !== PAGE) return
    if (msg.type === 'ping') {
      announce()
      return
    }
    if (msg.type !== 'command' || typeof msg.id !== 'string') return
    const reply = (result) => window.postMessage({ source: EXT, type: 'result', id: msg.id, result }, location.origin)
    try {
      chrome.runtime.sendMessage({ type: 'vz-command', tool: msg.tool, args: msg.args || {} })
        .then(reply, (err) => reply({ error: 'extension_unavailable', message: String(err?.message || err) }))
    } catch (err) {
      // The extension was reloaded or removed after this page loaded.
      reply({ error: 'extension_unavailable', message: 'Reload this Vandalizer page to reconnect the browser extension.' })
    }
  })

  announce()
})()
