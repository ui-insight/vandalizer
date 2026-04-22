import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { type ReactNode } from 'react'

// We test the AuthProvider (which provides useAuth) by rendering it with mocked API calls.
// useAuth itself is a thin wrapper around useContext, so the real value is testing the provider.

const mockLogin = vi.fn()
const mockRegister = vi.fn()
const mockLogout = vi.fn()
const mockGetMe = vi.fn()

vi.mock('../api/auth', () => ({
  login: (...args: unknown[]) => mockLogin(...args),
  register: (...args: unknown[]) => mockRegister(...args),
  logout: (...args: unknown[]) => mockLogout(...args),
  getMe: (...args: unknown[]) => mockGetMe(...args),
}))

import { useAuth } from './useAuth'
import { AuthProvider } from '../contexts/AuthContext'

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

// Stub localStorage for jsdom
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()
vi.stubGlobal('localStorage', localStorageMock)

beforeEach(() => {
  vi.clearAllMocks()
  localStorageMock.clear()
  // Default: getMe fails (not logged in)
  mockGetMe.mockRejectedValue(new Error('Not authenticated'))
})

describe('useAuth', () => {
  it('throws when used outside AuthProvider', () => {
    // Suppress console.error from React
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => {
      renderHook(() => useAuth())
    }).toThrow('useAuth must be used within AuthProvider')
    spy.mockRestore()
  })

  it('starts in loading state', () => {
    mockGetMe.mockReturnValue(new Promise(() => {})) // never resolves
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.loading).toBe(true)
    expect(result.current.user).toBe(null)
  })

  it('loads user from getMe on mount', async () => {
    const user = { id: '1', user_id: 'alice', email: 'alice@test.com', name: 'Alice' }
    mockGetMe.mockResolvedValueOnce(user)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual(user)
  })

  it('sets user to null when getMe fails', async () => {
    mockGetMe.mockRejectedValueOnce(new Error('401'))

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBe(null)
  })

  it('login sets user on success', async () => {
    const user = { id: '1', user_id: 'alice', email: 'alice@test.com', name: 'Alice' }
    mockLogin.mockResolvedValueOnce(user)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login('alice', 'password')
    })

    expect(mockLogin).toHaveBeenCalledWith('alice', 'password')
    expect(result.current.user).toEqual(user)
  })

  it('login detects demo_expired flag', async () => {
    const expiredUser = {
      id: '1', user_id: 'demo', email: 'demo@test.com', name: 'Demo',
      demo_expired: true, demo_feedback_token: 'token-123',
    }
    mockLogin.mockResolvedValueOnce(expiredUser)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login('demo', 'pass')
    })

    expect(result.current.demoExpired).toBe(true)
    expect(result.current.demoFeedbackToken).toBe('token-123')
  })

  it('register sets user on success', async () => {
    const user = { id: '2', user_id: 'bob', email: 'bob@test.com', name: 'Bob' }
    mockRegister.mockResolvedValueOnce(user)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.register('bob', 'bob@test.com', 'pass', 'Bob')
    })

    expect(mockRegister).toHaveBeenCalledWith('bob', 'bob@test.com', 'pass', 'Bob', undefined)
    expect(result.current.user).toEqual(user)
  })

  it('logout clears user', async () => {
    const user = { id: '1', user_id: 'alice', email: 'alice@test.com', name: 'Alice' }
    mockGetMe.mockResolvedValueOnce(user)
    mockLogout.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.user).toEqual(user))

    await act(async () => {
      await result.current.logout()
    })

    expect(result.current.user).toBe(null)
    expect(result.current.demoExpired).toBe(false)
  })

  it('refreshUser re-fetches user data', async () => {
    mockGetMe.mockRejectedValueOnce(new Error('401'))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBe(null)

    const updatedUser = { id: '1', user_id: 'alice', email: 'alice@test.com', name: 'Alice Updated' }
    mockGetMe.mockResolvedValueOnce(updatedUser)

    await act(async () => {
      await result.current.refreshUser()
    })

    expect(result.current.user).toEqual(updatedUser)
  })
})
