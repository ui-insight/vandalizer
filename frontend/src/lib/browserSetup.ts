import { detectBrowserExtension, isBrowserExtensionReady, runBrowserTool } from './browserExtension'

export const EXTENSION_ID = 'goafgpnhcmnoklmmjoolggbhehomjomm'
export type BrowserConnection = 'checking' | 'not-installed' | 'installed' | 'connected'
export async function browserConnection(): Promise<BrowserConnection> {
  if (await detectBrowserExtension(500)) return 'connected'
  type Runtime = { sendMessage: (id: string, message: object, callback: (result?: { installed?: boolean }) => void) => void; lastError?: unknown }
  const runtime = (window as Window & { chrome?: { runtime?: Runtime } }).chrome?.runtime
  if (!runtime) return 'not-installed'
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve('not-installed'), 1000)
    try { runtime.sendMessage(EXTENSION_ID, { type: 'vz-installed' }, result => {
      void runtime.lastError
      clearTimeout(timer)
      resolve(isBrowserExtensionReady() ? 'connected' : result?.installed ? 'installed' : 'not-installed')
    }) } catch { clearTimeout(timer); resolve('not-installed') }
  })
}
export function focusBrowserTab() { return runBrowserTool('browser_focus', {}) }

export const browserStoreUrl = (import.meta.env.VITE_BROWSER_STORE_URL as string | undefined) || ''
