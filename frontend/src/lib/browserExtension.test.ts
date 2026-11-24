import { afterEach, describe, expect, it, vi } from 'vitest'
import { detectBrowserExtension, resetBrowserExtensionForTests, runBrowserTool } from './browserExtension'

// jsdom's postMessage leaves source and origin empty; a real page sets both.
function fromThisPage(data: unknown, origin = window.location.origin) {
  window.dispatchEvent(new MessageEvent('message', { data, origin, source: window }))
}

// Stands in for content/bridge.js: answers pings and commands on this page.
function installBridge(answer: (tool: string, args: Record<string, unknown>) => unknown) {
  const handler = (event: MessageEvent) => {
    const msg = event.data
    if (msg?.source !== 'vandalizer-page') return
    if (msg.type === 'ping') setTimeout(() => fromThisPage({ source: 'vandalizer-extension', type: 'ready' }))
    if (msg.type === 'command') {
      setTimeout(() => fromThisPage({ source: 'vandalizer-extension', type: 'result', id: msg.id, result: answer(msg.tool, msg.args) }))
    }
  }
  window.addEventListener('message', handler)
  return () => window.removeEventListener('message', handler)
}

describe('browser extension bridge', () => {
  let remove: (() => void) | null = null
  afterEach(() => {
    remove?.()
    remove = null
    resetBrowserExtensionForTests()
  })

  it('reports no extension when nothing answers, and does not send commands to it', async () => {
    expect(await detectBrowserExtension(30)).toBe(false)
    expect(await runBrowserTool('browser_read', {})).toMatchObject({ error: 'browser_not_connected' })
  })

  it('finds the extension and returns each command result to its own call', async () => {
    remove = installBridge((tool, args) => ({ tool, args }))
    expect(await detectBrowserExtension(200)).toBe(true)
    const [opened, read] = await Promise.all([
      runBrowserTool('browser_open', { url: 'https://fin.example.edu' }),
      runBrowserTool('browser_read', { query: 'balance' }),
    ])
    expect(opened).toEqual({ tool: 'browser_open', args: { url: 'https://fin.example.edu' } })
    expect(read).toEqual({ tool: 'browser_read', args: { query: 'balance' } })
  })

  it('dispatches a click once when an established bridge is slow to answer pings', async () => {
    const answer = vi.fn(() => ({ ok: true }))
    const listener = (event: MessageEvent) => {
      const msg = event.data
      if (msg?.source === 'vandalizer-page' && msg.type === 'command') {
        fromThisPage({ source: 'vandalizer-extension', type: 'result', id: msg.id, result: answer() })
      }
    }
    window.addEventListener('message', listener)
    remove = () => window.removeEventListener('message', listener)
    const detected = detectBrowserExtension()
    fromThisPage({ source: 'vandalizer-extension', type: 'ready' })
    expect(await detected).toBe(true)
    expect(await runBrowserTool('browser_click', { ref: 1 })).toEqual({ ok: true })
    expect(answer).toHaveBeenCalledOnce()
  })

  it("sends the administrator's site list with a command, and nothing when there is none", async () => {
    remove = installBridge(() => ({ ok: true }))
    const sent: Record<string, unknown>[] = []
    const spy = (event: MessageEvent) => { if (event.data?.type === 'command') sent.push(event.data) }
    window.addEventListener('message', spy)
    await runBrowserTool('browser_open', { url: 'https://fin.example.edu' }, ['example.edu'])
    await runBrowserTool('browser_read', {})
    window.removeEventListener('message', spy)
    expect(sent[0].allowedHosts).toEqual(['example.edu'])
    expect('allowedHosts' in sent[1]).toBe(false)
  })

  it('ignores an extension announcement from another origin', async () => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'ping') setTimeout(() => fromThisPage({ source: 'vandalizer-extension', type: 'ready' }, 'https://evil.example'))
    }
    window.addEventListener('message', handler)
    remove = () => window.removeEventListener('message', handler)
    expect(await detectBrowserExtension(50)).toBe(false)
  })

  it('turns a malformed answer into an error instead of passing it on', async () => {
    remove = installBridge(() => 'not an object')
    await detectBrowserExtension(200)
    expect(await runBrowserTool('browser_read', {})).toEqual({ error: 'browser_bad_result' })
  })
})
