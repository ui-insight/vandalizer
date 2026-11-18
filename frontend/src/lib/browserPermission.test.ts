import { afterEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import html from '../../../chrome-extension/permission/permission.html?raw'
import script from '../../../chrome-extension/permission/permission.js?raw'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
it('keeps denied permission visible and never reports it as granted', async () => {
  document.body.innerHTML = new DOMParser().parseFromString(html, 'text/html').body.innerHTML
  vi.stubGlobal('location', { search: '?host=portal.example.edu&pattern=https%3A%2F%2Fportal.example.edu%2F*&id=request' })
  const close = vi.spyOn(window, 'close').mockImplementation(() => {})
  const chrome = { permissions: { request: vi.fn(async () => false) }, runtime: { sendMessage: vi.fn(async () => {}) } }
  new Function('chrome', script)(chrome)
  expect(chrome.permissions.request).not.toHaveBeenCalled()
  document.getElementById('allow')!.click()
  await waitFor(() => expect(document.getElementById('status')).toHaveTextContent('did not allow access'))
  expect(chrome.permissions.request).toHaveBeenCalledWith({ origins: ['https://portal.example.edu/*'] })
  expect(chrome.runtime.sendMessage).not.toHaveBeenCalled()
  expect(close).not.toHaveBeenCalled()
  document.getElementById('deny')!.click()
  await waitFor(() => expect(close).toHaveBeenCalled())
  expect(chrome.runtime.sendMessage).toHaveBeenCalledWith({ type: 'vz-permission-decision', id: 'request', granted: false })
})
