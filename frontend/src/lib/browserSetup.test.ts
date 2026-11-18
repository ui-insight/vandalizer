import { afterEach, expect, it, vi } from 'vitest'
import { browserConnection, EXTENSION_ID } from './browserSetup'
import { detectBrowserExtension, isBrowserExtensionReady } from './browserExtension'
vi.mock('./browserExtension', () => ({ detectBrowserExtension: vi.fn(), isBrowserExtensionReady: vi.fn(), runBrowserTool: vi.fn() }))
afterEach(() => { vi.clearAllMocks(); Reflect.deleteProperty(window, 'chrome') })
it('finds connected bridge without public discovery', async () => {
  vi.mocked(isBrowserExtensionReady).mockReturnValue(true)
  vi.mocked(detectBrowserExtension).mockResolvedValue(true)
  expect(await browserConnection()).toBe('connected')
})
it.each([true, false])('discovers installation without granting commands: %s', async installed => {
  vi.mocked(isBrowserExtensionReady).mockReturnValue(false)
  vi.mocked(detectBrowserExtension).mockResolvedValue(false)
  const sendMessage = vi.fn((_id, _message, callback) => callback({ installed }))
  Object.assign(window, { chrome: { runtime: { sendMessage } } })
  expect(await browserConnection()).toBe(installed ? 'installed' : 'not-installed')
  expect(sendMessage.mock.calls[0].slice(0, 2)).toEqual([EXTENSION_ID, { type: 'vz-installed' }])
})
it('handles browsers without extension discovery', async () => {
  vi.mocked(isBrowserExtensionReady).mockReturnValue(false)
  vi.mocked(detectBrowserExtension).mockResolvedValue(false)
  expect(await browserConnection()).toBe('not-installed')
})
