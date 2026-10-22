import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { useCertification } from '../hooks/useCertification'
import { certificationChatEntry } from '../lib/certificationChat'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise, CourseDefinition, PendingCompletion, OutcomeCompletionSelection } from '../types/certification'

export type PanelMode = 'floating' | 'fullscreen' | 'docked-left' | 'docked-right' | 'docked-bottom'
export interface AssessmentDestination { nonce: number; moduleId: string; enrollmentId: string; manifestSha256: string }
export interface CertificationChatRequest { nonce: number; message: string }

interface CertificationPanelContextValue {
  // Panel UI state
  isOpen: boolean
  mode: PanelMode
  openPanel: () => void
  // Open the course in chat: queue the start/continue kickoff message for the
  // workspace chat to send. Entry points outside the workspace navigate to '/'.
  openInChat: () => void
  chatRequest: CertificationChatRequest | null
  consumeChatRequest: (nonce: number) => void
  openAssessment: (moduleId: string, enrollmentId: string, manifestSha256: string) => void
  assessmentDestination: AssessmentDestination | null
  consumeAssessmentDestination: (nonce: number) => void
  closePanel: () => void
  togglePanel: () => void
  setMode: (mode: PanelMode) => void
  // Certification data — shared between panel and rail badge
  progress: CertificationProgress | null
  course: CourseDefinition | null
  loading: boolean
  refresh: () => Promise<void>
  refreshAfterWrite: () => Promise<void>
  refreshError: string | null
  savedWritePendingRefresh: boolean
  validate: (moduleId: string) => Promise<ValidationResult>
  pendingCompletions: PendingCompletion[]
  complete: (moduleId: string, requestId?: string, selection?: OutcomeCompletionSelection) => Promise<CompletionResult>
  provision: (moduleId: string) => Promise<unknown>
  getExercise: (moduleId: string) => Promise<CertExercise>
  submitAssessment: (moduleId: string, answers: Record<string, string>) => Promise<unknown>
  savePosition: (moduleId: string, lessonId: string) => Promise<void>
}

const CertificationPanelContext = createContext<CertificationPanelContextValue | null>(null)

const STORAGE_KEY = 'cert-panel-mode'

function getStoredMode(): PanelMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && ['floating', 'fullscreen', 'docked-left', 'docked-right', 'docked-bottom'].includes(stored)) {
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
  const [assessmentDestination, setAssessmentDestination] = useState<AssessmentDestination | null>(null)
  const destinationSequence = useRef(0)
  const openAssessment = useCallback((moduleId: string, enrollmentId: string, manifestSha256: string) => {
    const { course, progress } = cert
    if (!course || !progress || course.enrollment_id !== enrollmentId || progress.enrollment_id !== enrollmentId
      || course.course_version !== progress.course_version
      || course.manifest_sha256 !== manifestSha256 || progress.manifest_sha256 !== manifestSha256
      || !course.modules.some(module => module.id === moduleId)
      || !course.prerequisites[moduleId]?.every(id => progress.modules[id]?.completed)) return
    setAssessmentDestination({ nonce: ++destinationSequence.current, moduleId, enrollmentId, manifestSha256 })
    setIsOpen(true)
  }, [cert])
  const consumeAssessmentDestination = useCallback((nonce: number) => {
    setAssessmentDestination(current => current?.nonce === nonce ? null : current)
  }, [])

  const setMode = useCallback((m: PanelMode) => {
    setModeState(m)
    try { localStorage.setItem(STORAGE_KEY, m) } catch {}
  }, [])

  const [chatRequest, setChatRequest] = useState<CertificationChatRequest | null>(null)
  const chatSequence = useRef(0)
  const openInChat = useCallback(() => {
    setIsOpen(false)
    setChatRequest({ nonce: ++chatSequence.current, message: certificationChatEntry(cert.progress, cert.course).message })
  }, [cert.progress, cert.course])
  const consumeChatRequest = useCallback((nonce: number) => {
    setChatRequest(current => current?.nonce === nonce ? null : current)
  }, [])

  const openPanel = useCallback(() => { setIsOpen(true) }, [])
  const closePanel = useCallback(() => { setIsOpen(false) }, [])
  const togglePanel = useCallback(() => { setIsOpen(prev => !prev) }, [])

  return (
    <CertificationPanelContext.Provider value={{
      isOpen, mode, openPanel, openInChat, chatRequest, consumeChatRequest, openAssessment, assessmentDestination, consumeAssessmentDestination, closePanel, togglePanel, setMode,
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

/** Null-safe variant for components (e.g. chat tool cards) that should work
 *  even when rendered outside the provider, as in unit tests. */
export function useCertificationPanelOptional() {
  return useContext(CertificationPanelContext)
}
