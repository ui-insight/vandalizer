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

// Longer than the server's wait for a site permission (150s), so the server
// decides when a call has taken too long.
const COMMAND_TIMEOUT_MS = 170_000

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
      if (result && typeof result === 'object' && 'error' in result && result.error === 'extension_unavailable') ready = false
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
  return new Promise((resolve) => {
    const done = () => { clearTimeout(timer); readyWaiters.delete(done); resolve(true) }
    const timer = setTimeout(() => { readyWaiters.delete(done); ready = false; resolve(false) }, timeoutMs)
    readyWaiters.add(done)
    window.postMessage({ source: PAGE, type: 'ping' }, window.location.origin)
  })
}

/** Run one browser tool call in the extension. Never rejects. */
export async function runBrowserTool(tool: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
  listen()
  if (!(await detectBrowserExtension(500))) return Promise.resolve({ error: 'browser_not_connected', message: 'The Vandalizer browser extension is not connected on this page.' })
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      pending.delete(id)
      resolve({ error: 'browser_timeout', message: 'The browser extension did not answer.' })
    }, COMMAND_TIMEOUT_MS)
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
