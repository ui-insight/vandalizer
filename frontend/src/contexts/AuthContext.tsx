import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'
import type { User } from '../types/user'
import * as authApi from '../api/auth'

interface AuthContextValue {
  user: User | null
  loading: boolean
  demoExpired: boolean
  demoFeedbackToken: string | null
  login: (userId: string, password: string) => Promise<void>
  register: (userId: string, email: string, password: string, name?: string, inviteToken?: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [demoExpired, setDemoExpired] = useState(false)
  const [demoFeedbackToken, setDemoFeedbackToken] = useState<string | null>(null)

  useEffect(() => {
    authApi
      .getMe()
      .then(setUser)
      .catch((err) => {
        setUser(null)
        // Check if 403 with DEMO_EXPIRED
        if (err?.status === 403 && err?.message === 'DEMO_EXPIRED') {
          setDemoExpired(true)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (userId: string, password: string) => {
    const resp = await authApi.login(userId, password) as User & {
      demo_expired?: boolean
      demo_feedback_token?: string | null
    }

    if (resp.demo_expired) {
      setDemoExpired(true)
      setDemoFeedbackToken(resp.demo_feedback_token || null)
      setUser(resp)
      return
    }

    setDemoExpired(false)
    setDemoFeedbackToken(null)
    localStorage.removeItem('workspace:mode')
    setUser(resp)
  }, [])

  const register = useCallback(
    async (userId: string, email: string, password: string, name?: string, inviteToken?: string) => {
      const u = await authApi.register(userId, email, password, name, inviteToken)
      localStorage.removeItem('workspace:mode')
      setUser(u)
    },
    [],
  )

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
    setDemoExpired(false)
    setDemoFeedbackToken(null)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const u = await authApi.getMe()
      setUser(u)
    } catch {
      // ignore
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, demoExpired, demoFeedbackToken, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}
