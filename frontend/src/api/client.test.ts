import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, ApiError } from './client'

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  mockFetch.mockReset()
  // Clear cookies
  document.cookie = 'csrf_token=; max-age=0'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('apiFetch', () => {
  it('sends credentials: include on all requests', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await apiFetch('/api/test')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('sends Content-Type: application/json by default', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await apiFetch('/api/test')

    const call = mockFetch.mock.calls[0]
    const headers = call[1].headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('sends X-CSRF-Token header when csrf_token cookie exists', async () => {
    document.cookie = 'csrf_token=test-csrf-value'
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await apiFetch('/api/test')

    const call = mockFetch.mock.calls[0]
    const headers = call[1].headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('test-csrf-value')
  })

  it('does not send X-CSRF-Token when no cookie exists', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await apiFetch('/api/test')

    const call = mockFetch.mock.calls[0]
    const headers = call[1].headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBeUndefined()
  })

  it('retries on 401 with token refresh', async () => {
    // First call returns 401
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 401))
    // Refresh call succeeds
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 200))
    // Retry succeeds
    mockFetch.mockResolvedValueOnce(jsonResponse({ data: 'success' }))

    const result = await apiFetch('/api/test')

    expect(result).toEqual({ data: 'success' })
    expect(mockFetch).toHaveBeenCalledTimes(3)

    // Verify the refresh call
    const refreshCall = mockFetch.mock.calls[1]
    expect(refreshCall[0]).toBe('/api/auth/refresh')
    expect(refreshCall[1].method).toBe('POST')
  })

  it('includes CSRF token on retry after 401', async () => {
    document.cookie = 'csrf_token=retry-csrf'

    mockFetch.mockResolvedValueOnce(jsonResponse({}, 401))
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 200)) // refresh
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    await apiFetch('/api/test')

    // The retry (3rd call) should include CSRF token
    const retryCall = mockFetch.mock.calls[2]
    const headers = retryCall[1].headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('retry-csrf')
  })

  it('throws ApiError(401) when refresh fails', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 401))
    mockFetch.mockResolvedValueOnce(jsonResponse({}, 401)) // refresh fails

    await expect(apiFetch('/api/test')).rejects.toThrow(ApiError)
    await expect(apiFetch('/api/test')).rejects.toThrow()
  })

  it('throws ApiError(403) with DEMO_EXPIRED detail', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'DEMO_EXPIRED' }, 403))

    try {
      await apiFetch('/api/test')
      expect.fail('should have thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).status).toBe(403)
      expect((err as ApiError).message).toBe('DEMO_EXPIRED')
    }
  })

  it('throws ApiError on other error status codes', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Not found' }, 404))

    try {
      await apiFetch('/api/test')
      expect.fail('should have thrown')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).status).toBe(404)
    }
  })
})

describe('ApiError', () => {
  it('has status and message properties', () => {
    const err = new ApiError(500, 'Server error')
    expect(err.status).toBe(500)
    expect(err.message).toBe('Server error')
    expect(err).toBeInstanceOf(Error)
  })
})
