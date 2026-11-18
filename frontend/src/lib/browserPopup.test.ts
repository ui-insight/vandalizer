import popupHtml from '../../../chrome-extension/popup/popup.html?raw'
import connectHtml from '../../../chrome-extension/popup/connect.html?raw'
import popupScript from '../../../chrome-extension/popup/popup.js?raw'
import { afterEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'

async function popup(search = '', granted = true, savedOrigin = '', access = true, activeUrl = 'https://vandalizer.example.edu/chat') {
  const html = new DOMParser().parseFromString(search ? connectHtml : popupHtml, 'text/html')
  document.body.innerHTML = html.body.innerHTML
  document.body.dataset.page = search ? 'connect' : 'popup'
  vi.stubGlobal('location', { search })
  const close = vi.spyOn(window, 'close').mockImplementation(() => {})
  const chrome = {
    tabs: { query: vi.fn(async () => [{ id: 42, windowId: 7, url: activeUrl }]), create: vi.fn(), get: vi.fn(async () => ({ id: 43, windowId: 7 })), update: vi.fn() },
    windows: { update: vi.fn() },
    runtime: { getURL: (path: string) => `chrome-extension://test/${path}` },
    permissions: { contains: vi.fn(async () => access), getAll: vi.fn(async () => ({ origins: [] })), request: vi.fn(async () => granted), remove: vi.fn() },
    storage: { local: { get: vi.fn(async () => ({ vandalizerOrigin: savedOrigin })), set: vi.fn() }, session: { get: vi.fn(async () => ({ workingTabId: 43 })) } },
    scripting: { getRegisteredContentScripts: vi.fn(async () => []), registerContentScripts: vi.fn(), executeScript: vi.fn() },
  }
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
  await new AsyncFunction('chrome', popupScript.replace('\nload().catch', '\nawait load().catch'))(chrome)
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

it('makes connected status and opening Vandalizer primary, without another connect prompt', async () => {
  const { chrome } = await popup('', true, 'https://vandalizer.example.edu')
  expect(document.getElementById('connection-label')).toHaveTextContent('Connected')
  expect(document.getElementById('connected-actions')).toBeVisible()
  expect(document.getElementById('change-connection')).not.toBeVisible()
  document.getElementById('open-vandalizer')!.click()
  await waitFor(() => expect(chrome.tabs.update).toHaveBeenCalledWith(42, { active: true }))
  expect(chrome.windows.update).toHaveBeenCalledWith(7, { focused: true })
  expect(chrome.permissions.request).not.toHaveBeenCalled()
})
it('keeps a portal from replacing the existing connection unless the person explicitly expands the form', async () => {
  await popup('', true, 'https://vandalizer.example.edu', true, 'https://portal.example.edu/awards')
  expect(document.getElementById('connection-site')).toHaveTextContent('https://vandalizer.example.edu')
  expect(document.getElementById('change-connection')).not.toHaveAttribute('open')
  expect(document.getElementById('connect')).not.toBeVisible()
})
it('shows reconnect help after a host permission is revoked', async () => {
  await popup('', true, 'https://vandalizer.example.edu', false)
  expect(document.getElementById('connection-label')).toHaveTextContent('Connection needs attention')
  expect(document.getElementById('connect')).toBeVisible()
  expect(document.getElementById('connected-actions')).not.toBeVisible()
})
it('replaces approval with a return action after connecting', async () => {
  const { submit } = await popup('?origin=https%3A%2F%2Fvandalizer.example.edu')
  submit()
  await waitFor(() => expect(document.getElementById('page-title')).toHaveTextContent('Your browser is ready'))
  expect(document.getElementById('connect')).not.toBeVisible()
  expect(document.getElementById('open-vandalizer')).toHaveTextContent('Return to Vandalizer')
})
it('offers the existing working tab without reading it', async () => {
  const { chrome } = await popup('', true, 'https://vandalizer.example.edu')
  document.getElementById('open-working')!.click()
  await waitFor(() => expect(chrome.tabs.update).toHaveBeenCalledWith(43, { active: true }))
  expect(chrome.scripting.executeScript).not.toHaveBeenCalled()
})
it('does not ask a connected user to reconnect from a browser settings tab', async () => {
  await popup('', true, 'https://vandalizer.example.edu', true, 'chrome://extensions')
  expect(document.getElementById('connection-label')).toHaveTextContent('Connected')
  expect(document.getElementById('status')).toBeEmptyDOMElement()
})
