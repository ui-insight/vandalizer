import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useCertification } from '../hooks/useCertification'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise } from '../types/certification'

export type PanelMode = 'floating' | 'docked-left' | 'docked-right' | 'docked-bottom'

interface CertificationPanelContextValue {
  // Panel UI state
  isOpen: boolean
  mode: PanelMode
  openPanel: () => void
  closePanel: () => void
  togglePanel: () => void
  setMode: (mode: PanelMode) => void
  // Certification data — shared between panel and rail badge
  progress: CertificationProgress | null
  loading: boolean
  refresh: () => Promise<void>
  validate: (moduleId: string) => Promise<ValidationResult>
  complete: (moduleId: string) => Promise<CompletionResult>
  provision: (moduleId: string) => Promise<unknown>
  getExercise: (moduleId: string) => Promise<CertExercise>
  submitAssessment: (moduleId: string, answers: Record<string, string>) => Promise<unknown>
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

  // Single useCertification call — shared by panel and rail via context
  const cert = useCertification()

  const setMode = useCallback((m: PanelMode) => {
    setModeState(m)
    try { localStorage.setItem(STORAGE_KEY, m) } catch {}
  }, [])

  const openPanel = useCallback(() => { setIsOpen(true) }, [])
  const closePanel = useCallback(() => { setIsOpen(false) }, [])
  const togglePanel = useCallback(() => { setIsOpen(prev => !prev) }, [])

  return (
    <CertificationPanelContext.Provider value={{
      isOpen, mode, openPanel, closePanel, togglePanel, setMode,
      ...cert,
    }}>
      {children}
    </CertificationPanelContext.Provider>
  )
}

export function useCertificationPanel() {
  const ctx = useContext(CertificationPanelContext)
  if (!ctx) throw new Error('useCertificationPanel must be used within CertificationPanelProvider')
  return ctx
}
