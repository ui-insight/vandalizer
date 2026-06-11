import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'

export type AppMode = 'ra' | 'developer'

interface AppModeContextValue {
  mode: AppMode
  isRA: boolean
  canToggle: boolean
  setMode: (m: AppMode) => void
}

const AppModeContext = createContext<AppModeContextValue | null>(null)

const STORAGE_KEY = 'appMode'

export function AppModeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const isRARole = user?.app_role === 'research_admin'

  const [mode, setModeState] = useState<AppMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'ra' ? 'ra' : 'developer'
  })

  useEffect(() => {
    if (isRARole) {
      setModeState('ra')
    }
  }, [isRARole])

  const setMode = useCallback(
    (m: AppMode) => {
      if (isRARole) return
      localStorage.setItem(STORAGE_KEY, m)
      setModeState(m)
    },
    [isRARole],
  )

  return (
    <AppModeContext.Provider value={{ mode, isRA: mode === 'ra', canToggle: !isRARole, setMode }}>
      {children}
    </AppModeContext.Provider>
  )
}

export function useAppMode() {
  const ctx = useContext(AppModeContext)
  if (!ctx) throw new Error('useAppMode must be used inside AppModeProvider')
  return ctx
}
