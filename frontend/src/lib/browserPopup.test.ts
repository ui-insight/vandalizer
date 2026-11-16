import popupScript from '../../../chrome-extension/popup/popup.js?raw'
import { afterEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'

async function popup(search = '', granted = true) {
  document.body.innerHTML = '<h1>Vandalizer Browser</h1><p id="connect-help"></p><form id="connect"><input id="origin"><button type="submit">Connect this site</button></form><p id="status"></p><ul id="sites"></ul>'
  vi.stubGlobal('location', { search })
  const close = vi.spyOn(window, 'close').mockImplementation(() => {})
  const chrome = {
    tabs: { query: vi.fn(async () => [{ id: 42, url: 'https://vandalizer.example.edu/chat' }]), create: vi.fn() },
    runtime: { getURL: (path: string) => `chrome-extension://test/${path}` },
    permissions: { contains: vi.fn(async () => true), getAll: vi.fn(async () => ({ origins: [] })), request: vi.fn(async () => granted), remove: vi.fn() },
    storage: { local: { get: vi.fn(async () => ({})), set: vi.fn() } },
    scripting: { getRegisteredContentScripts: vi.fn(async () => []), registerContentScripts: vi.fn(), executeScript: vi.fn() },
  }
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
  await new AsyncFunction('chrome', popupScript.replace(/\nload\(\)\s*$/, '\nawait load()'))(chrome)
  const submit = () => document.getElementById('connect')!.dispatchEvent(new Event('submit', { cancelable: true }))
  return { chrome, close, submit }
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
it('gets the address from the active tab and opens a persistent connection page', async () => {
  const { chrome, close, submit } = await popup()
  expect((document.getElementById('origin') as HTMLInputElement).value).toBe('https://vandalizer.example.edu')
  submit()
  await waitFor(() => expect(close).toHaveBeenCalled())
  expect(chrome.tabs.create).toHaveBeenCalledWith({ url: 'chrome-extension://test/popup/connect.html?origin=https%3A%2F%2Fvandalizer.example.edu' })
  expect(chrome.permissions.request).not.toHaveBeenCalled()
})
it('grants only the confirmed site, registers future loads and injects into existing tabs', async () => {
  const { chrome, submit } = await popup('?origin=https%3A%2F%2Fvandalizer.example.edu')
  submit()
  await waitFor(() => expect(document.getElementById('status')).toHaveTextContent('No reload needed'))
  expect(chrome.permissions.request).toHaveBeenCalledWith({ origins: ['https://vandalizer.example.edu/*'] })
  expect(chrome.storage.local.set).toHaveBeenCalledWith({ vandalizerOrigin: 'https://vandalizer.example.edu' })
  expect(chrome.scripting.executeScript).toHaveBeenCalledWith({ target: { tabId: 42 }, files: ['content/bridge.js'] })
})
it('explains a denied grant and leaves the connection unchanged', async () => {
  const { chrome, submit } = await popup('?origin=https%3A%2F%2Fvandalizer.example.edu', false)
  submit()
  await waitFor(() => expect(document.getElementById('status')).toHaveTextContent('Chrome did not allow'))
  expect(chrome.storage.local.set).not.toHaveBeenCalled()
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
})
