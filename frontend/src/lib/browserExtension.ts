// Talks to the Vandalizer Browser extension (chrome-extension/) through the
// bridge script it injects into this page. Chat's browser tools run there,
// in the person's own Chrome; the result goes back to the waiting tool via
// POST /api/chat/browser-results.

const PAGE = 'vandalizer-page'
const EXT = 'vandalizer-extension'

/** Tools the extension carries out. record_value runs on the server. */
export const BROWSER_TOOL_NAMES: ReadonlySet<string> = new Set([
  'browser_open', 'browser_read', 'browser_click', 'browser_type', 'browser_select',
])

// Five seconds shorter than the server's wait for each tool
// (chat_browser_tools.py: 180s to open, 60s otherwise), so a command the
// extension never answers is reported as a timeout while the server still
// listens, and stops holding up the calls queued behind it.
const OPEN_TIMEOUT_MS = 175_000
const ACTION_TIMEOUT_MS = 55_000
export function browserCommandTimeoutMs(tool: string): number {
  return tool === 'browser_open' ? OPEN_TIMEOUT_MS : ACTION_TIMEOUT_MS
}

type ExtensionMessage = { source?: string; type?: string; id?: string; result?: unknown }

let ready = false
const pending = new Map<string, (result: Record<string, unknown>) => void>()
const readyWaiters = new Set<() => void>()
let listening = false

function listen() {
  if (listening || typeof window === 'undefined') return
  listening = true
  window.addEventListener('message', (event: MessageEvent<ExtensionMessage>) => {
    if (event.source !== window || event.origin !== window.location.origin) return
    const msg = event.data
    if (!msg || msg.source !== EXT) return
    if (msg.type === 'ready') {
      ready = true
      readyWaiters.forEach((resolve) => resolve())
      readyWaiters.clear()
    } else if (msg.type === 'result' && typeof msg.id === 'string') {
      const resolve = pending.get(msg.id)
      if (!resolve) return
      pending.delete(msg.id)
      const result = msg.result
      resolve(result && typeof result === 'object' && !Array.isArray(result)
        ? result as Record<string, unknown>
        : { error: 'browser_bad_result' })
    }
  })
}

/** Whether the extension has announced itself on this page (no waiting). */
export function isBrowserExtensionReady(): boolean {
  listen()
  return ready
}

/** Ask whether the extension's bridge is on this page; resolves within timeoutMs. */
export function detectBrowserExtension(timeoutMs = 300): Promise<boolean> {
  listen()
  if (ready) return Promise.resolve(true)
  return new Promise((resolve) => {
    const done = () => { clearTimeout(timer); readyWaiters.delete(done); resolve(true) }
    const timer = setTimeout(() => { readyWaiters.delete(done); resolve(ready) }, timeoutMs)
    readyWaiters.add(done)
    window.postMessage({ source: PAGE, type: 'ping' }, window.location.origin)
  })
}

/** Run one browser tool call in the extension. Never rejects. */
export function runBrowserTool(tool: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
  listen()
  if (!ready) return Promise.resolve({ error: 'browser_not_connected', message: 'The Vandalizer browser extension is not connected on this page.' })
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      pending.delete(id)
      resolve({ error: 'browser_timeout', message: 'The browser extension did not answer.' })
    }, browserCommandTimeoutMs(tool))
    pending.set(id, (result) => { clearTimeout(timer); resolve(result) })
    window.postMessage({ source: PAGE, type: 'command', id, tool, args }, window.location.origin)
  })
}

/** Test hook: forget what this module learned about the extension. */
export function resetBrowserExtensionForTests() {
  ready = false
  pending.clear()
  readyWaiters.clear()
}
