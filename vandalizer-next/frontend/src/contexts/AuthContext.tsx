import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'
import type { User } from '../types/user'
import * as authApi from '../api/auth'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (userId: string, password: string) => Promise<void>
  register: (userId: string, email: string, password: string, name?: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    authApi
      .getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (userId: string, password: string) => {
    const u = await authApi.login(userId, password)
    setUser(u)
  }, [])

  const register = useCallback(
    async (userId: string, email: string, password: string, name?: string) => {
      const u = await authApi.register(userId, email, password, name)
      setUser(u)
    },
    [],
  )

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
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
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}
