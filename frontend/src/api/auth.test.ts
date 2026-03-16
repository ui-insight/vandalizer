import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

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
  document.cookie = 'csrf_token=; max-age=0'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('auth API', () => {
  it('login sends POST with credentials', async () => {
    const user = { id: '1', user_id: 'testuser', email: 'test@example.com', name: 'Test' }
    mockFetch.mockResolvedValueOnce(jsonResponse(user))

    const { login } = await import('./auth')
    const result = await login('testuser', 'password123')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/auth/login')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body.user_id).toBe('testuser')
    expect(body.password).toBe('password123')
    expect(result.user_id).toBe('testuser')
  })

  it('register sends POST with user details', async () => {
    const user = { id: '2', user_id: 'newuser', email: 'new@example.com', name: 'New User' }
    mockFetch.mockResolvedValueOnce(jsonResponse(user))

    const { register } = await import('./auth')
    const result = await register('newuser', 'new@example.com', 'securepass', 'New User')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/auth/register')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body.user_id).toBe('newuser')
    expect(body.email).toBe('new@example.com')
    expect(body.password).toBe('securepass')
    expect(body.name).toBe('New User')
    expect(result.user_id).toBe('newuser')
  })

  it('getMe calls GET /api/auth/me', async () => {
    const user = { id: '1', user_id: 'testuser', email: 'test@example.com', name: 'Test' }
    mockFetch.mockResolvedValueOnce(jsonResponse(user))

    const { getMe } = await import('./auth')
    const result = await getMe()

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/auth/me')
    // Should default to GET (no method specified means GET)
    expect(call[1].method).toBeUndefined()
    expect(result.user_id).toBe('testuser')
  })

  it('logout sends POST /api/auth/logout', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))

    const { logout } = await import('./auth')
    const result = await logout()

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/auth/logout')
    expect(call[1].method).toBe('POST')
    expect(result.ok).toBe(true)
  })
})
