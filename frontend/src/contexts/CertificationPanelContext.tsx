import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

export type PanelMode = 'floating' | 'docked-left' | 'docked-right' | 'docked-bottom'

interface CertificationPanelContextValue {
  isOpen: boolean
  mode: PanelMode
  openPanel: () => void
  closePanel: () => void
  togglePanel: () => void
  setMode: (mode: PanelMode) => void
}

const CertificationPanelContext = createContext<CertificationPanelContextValue | null>(null)

const STORAGE_KEY = 'cert-panel-mode'

function getStoredMode(): PanelMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && ['floating', 'docked-left', 'docked-right', 'docked-bottom'].includes(stored)) {
      return stored as PanelMode
    }
  } catch {}
  return 'floating'
}

export function CertificationPanelProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [mode, setModeState] = useState<PanelMode>(getStoredMode)

  const setMode = useCallback((m: PanelMode) => {
    setModeState(m)
    try { localStorage.setItem(STORAGE_KEY, m) } catch {}
  }, [])

  const openPanel = useCallback(() => {
    setIsOpen(true)
    // Restore last mode (already in state from init)
  }, [])

  const closePanel = useCallback(() => {
    setIsOpen(false)
  }, [])

  const togglePanel = useCallback(() => {
    setIsOpen(prev => !prev)
  }, [])

  return (
    <CertificationPanelContext.Provider value={{ isOpen, mode, openPanel, closePanel, togglePanel, setMode }}>
      {children}
    </CertificationPanelContext.Provider>
  )
}

export function useCertificationPanel() {
  const ctx = useContext(CertificationPanelContext)
  if (!ctx) throw new Error('useCertificationPanel must be used within CertificationPanelProvider')
  return ctx
}
