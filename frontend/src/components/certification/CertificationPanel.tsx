import { ValidationResults } from './ValidationResults'
import { CompletionResumeNotice } from './CompletionResumeNotice'
import { CourseSelectionNotice } from './CourseSelectionNotice'
import { ApiError } from '../../api/client'
import { CertificationRefreshNotice } from './CertificationRefreshNotice'
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { createPortal } from '../shared/panelPortal'
import { useQueryClient } from '@tanstack/react-query'
import {
  Award,
  ChevronLeft,
  GripHorizontal,
  X,
  ExternalLink,
} from 'lucide-react'
import { useCertificationPanel, type PanelMode } from '../../contexts/CertificationPanelContext'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../contexts/ToastContext'
import { cn } from '../../lib/cn'
import type { ValidationResult, CompletionResult, CertExercise } from '../../types/certification'
import { LEVEL_CONFIG, LEVEL_THRESHOLDS as LEGACY_LEVELS, TIERS as LEGACY_TIERS } from './constants'
import { CertifiedBanner } from './CertifiedBanner'
import { CredentialHistory } from './CredentialHistory'
import { UpgradeComparison } from './UpgradeComparison'
import { SavedCourseChoices } from './SavedCourseChoices'
import { CourseLearningPolicy } from './CourseLearningPolicy'
import { CourseBridgePath } from './CourseBridgePath'
import { observeCertificationJourney } from '../../api/certificationJourney'
import { CourseHistory } from './CourseHistory'
import { CelebrationOverlay } from './CelebrationOverlay'
import { ModuleDetail } from './ModuleDetail'
import { JourneyMap } from './JourneyMap'
import { XpMilestones } from './XpMilestones'
import { useModuleLock } from './useModuleLock'
import { MODULES as LEGACY_MODULES } from './modules'
import { FocusTrap } from '../shared/PanelFocusTrap'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProgressRing({ percentage, size = 160, strokeWidth = 10, color }: {
  percentage: number
  size?: number
  strokeWidth?: number
  color: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percentage / 100) * circumference
  const [animatedOffset, setAnimatedOffset] = useState(circumference)

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setAnimatedOffset(offset); return }
    const timer = setTimeout(() => setAnimatedOffset(offset), 100)
    return () => clearTimeout(timer)
  }, [offset])

  return (
    <svg width={size} height={size} className="cert-ring-spin" role="progressbar" aria-label="Course modules completed" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percentage)}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={strokeWidth} />
      <circle
        cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color}
        strokeWidth={strokeWidth} strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={animatedOffset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
      />
    </svg>
  )
}

function XPBar({ current, nextThreshold, prevThreshold, nextLevel }: {
  current: number; nextThreshold: number; prevThreshold: number; nextLevel?: string
}) {
  const range = nextThreshold - prevThreshold
  const progress = range > 0 ? Math.max(0, Math.min(((current - prevThreshold) / range) * 100, 100)) : 100
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-gray-500">{current} XP</span>
        <span className="text-xs text-gray-500">
          {nextLevel ? `${Math.max(0, nextThreshold - current)} XP to ${LEVEL_CONFIG[nextLevel]?.label || nextLevel}` : 'Highest XP threshold reached'}
        </span>
      </div>
      <div className="h-2.5 bg-gray-200 overflow-hidden" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
        <div className="h-full cert-xp-glow" style={{
          width: `${progress}%`,
          background: 'linear-gradient(90deg, var(--highlight-color), var(--highlight-complement))',
          borderRadius: 'var(--ui-radius, 12px)',
          transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)',
        }} />
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Mode toggle buttons
// ---------------------------------------------------------------------------

const PANEL_POSITIONS: { mode: PanelMode; label: string }[] = [
  { mode: 'floating', label: 'Floating window' },
  { mode: 'fullscreen', label: 'Full screen' },
  { mode: 'docked-left', label: 'Dock left' },
  { mode: 'docked-right', label: 'Dock right' },
  { mode: 'docked-bottom', label: 'Dock bottom' },
]

// ---------------------------------------------------------------------------
// Main panel component
// ---------------------------------------------------------------------------

export function CertificationPanel({ onOpenWorkspace }: { onOpenWorkspace?: () => Promise<void> }) {
  const { isOpen, mode, closePanel, setMode, progress, course, pendingCompletions, savedWritePendingRefresh, loading, validate, complete, provision, getExercise, submitAssessment, savePosition, refresh, assessmentDestination, consumeAssessmentDestination } = useCertificationPanel()
  const MODULES = course?.modules ?? LEGACY_MODULES
  const LEVEL_THRESHOLDS = course?.levels ?? LEGACY_LEVELS
  const TIERS = course?.tiers ?? LEGACY_TIERS
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const uid = user?.user_id || ''
  const panelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const panel = panelRef.current
    panel?.focus({ preventScroll: true })
    return () => {
      requestAnimationFrame(() => {
        if (panel?.isConnected || (document.activeElement !== document.body && !panel?.contains(document.activeElement))) return
        // The activity drawer closes when it opens the course, and a resize
        // can hide the original desktop trigger. Return to a visible entry.
        const visible = (element: HTMLElement | null) => element?.isConnected && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden'
        const target = visible(previous) ? previous : Array.from(document.querySelectorAll<HTMLElement>('[aria-label="Open learning panel"], [aria-label="Open activity"], [aria-label="Expand activity"]')).find(element => visible(element))
        target?.focus({ preventScroll: true })
      })
    }
  }, [isOpen])


  // Module interaction state — persist across reloads, scoped by user
  const [activeModule, setActiveModuleState] = useState<string | null>(() => {
    try { return localStorage.getItem(`cert-active-module:${uid}`) } catch { return null }
  })
  const [assessmentEntry, setAssessmentEntry] = useState<{ moduleId: string; nonce: number } | null>(null)
  const [selectionRefresh, setSelectionRefresh] = useState(0)
  async function refreshCourseChoice() {
    setSelectionRefresh(value => value + 1)
    await refresh()
  }
  useEffect(() => {
    if (progress?.enrollment_id) return
    try { setActiveModuleState(localStorage.getItem(`cert-active-module:${uid}`)) } catch { setActiveModuleState(null) }
  }, [uid, progress?.enrollment_id])
  const restoredEnrollment = useRef<string | null>(null)
  useEffect(() => {
    if (!progress?.enrollment_id || restoredEnrollment.current === progress.enrollment_id) return
    restoredEnrollment.current = progress.enrollment_id
    setAssessmentEntry(null)
    setActiveModuleState(progress.learning_position?.module_id ?? null)
  }, [progress])
  const setActiveModule = useCallback((id: string | null) => {
    setAssessmentEntry(null)
    setActiveModuleState(id)
    try { if (id) localStorage.setItem(`cert-active-module:${uid}`, id); else localStorage.removeItem(`cert-active-module:${uid}`) } catch {}
  }, [uid])
  // A chat save while this pane is closed should be honored on reopening.
  // Progress refreshes while the pane is open must not replace an active draft.
  const observedCursor = useRef<string | null>(null)
  const resumeOnOpen = useRef(false)
  const wasOpen = useRef(false)
  useEffect(() => {
    const cursor = progress?.enrollment_id ? `${progress.enrollment_id}:${progress.position_revision ?? 0}` : null
    if (!isOpen && cursor !== observedCursor.current && progress?.learning_position) resumeOnOpen.current = true
    if (isOpen && !wasOpen.current) {
      if (resumeOnOpen.current && progress?.learning_position) setActiveModuleState(progress.learning_position.module_id)
      if (!progress?.enrollment_id) {
        try { setActiveModuleState(localStorage.getItem(`cert-active-module:${uid}`)) } catch { /* Preserve the current pane when storage is unavailable. */ }
      }
      resumeOnOpen.current = false
    }
    observedCursor.current = cursor
    wasOpen.current = isOpen
  }, [isOpen, progress, uid])
  useEffect(() => {
    if (!isOpen || !assessmentDestination) return
    const target = assessmentDestination
    if (course?.enrollment_id === target.enrollmentId && progress?.enrollment_id === target.enrollmentId
      && course.course_version === progress.course_version
      && course.manifest_sha256 === target.manifestSha256 && progress.manifest_sha256 === target.manifestSha256
      && course.modules.some(module => module.id === target.moduleId)
      && course.prerequisites[target.moduleId]?.every(id => progress.modules[id]?.completed)) {
      setActiveModuleState(target.moduleId)
      setAssessmentEntry({ moduleId: target.moduleId, nonce: target.nonce })
    }
    consumeAssessmentDestination(target.nonce)
  }, [isOpen, assessmentDestination, consumeAssessmentDestination, course, progress])
  const validationScope = JSON.stringify([uid, progress?.enrollment_id, progress?.course_version, progress?.manifest_sha256, activeModule])
  const currentValidationScope = useRef(validationScope)
  currentValidationScope.current = validationScope
  const [validationRecord, setValidationResult] = useState<{ scope: string; result: ValidationResult } | null>(null)
  const [validationNotice, setValidationNotice] = useState<{ scope: string; state: 'checking' | 'unavailable' } | null>(null)
  const validationResult = validationRecord?.scope === validationScope ? validationRecord.result : null
  const validationRecheckState = validationNotice?.scope === validationScope ? validationNotice.state : undefined
  const [completionResult, setCompletionResult] = useState<CompletionResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [provisioning, setProvisioning] = useState(false)
  const [submittingAssessment, setSubmittingAssessment] = useState(false)
  const pendingPanelActions = useRef(new Set<string>())
  const [exercise, setExercise] = useState<CertExercise | null>(null)
  const [tierCelebration, setTierCelebration] = useState<{ tierName: string; message: string } | null>(null)
  const moduleScrollRef = useRef<HTMLDivElement>(null)
  const credentialSectionRef = useRef<HTMLDetailsElement>(null)
  const handleStepChange = useCallback(() => {
    moduleScrollRef.current?.scrollTo({ top: 0, behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }, [])

  // Drag state for floating mode
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null)
  const dragRef = useRef<{ startX: number; startY: number; panelX: number; panelY: number } | null>(null)
  useEffect(() => {
    if (!isOpen || mode !== 'floating') return
    const keepInViewport = () => {
      const rect = panelRef.current?.getBoundingClientRect()
      if (!rect) return
      setDragPos(previous => {
        if (!previous) return previous
        const x = Math.max(0, Math.min(window.innerWidth - rect.width, previous.x))
        const y = Math.max(0, Math.min(window.innerHeight - rect.height, previous.y))
        return x === previous.x && y === previous.y ? previous : { x, y }
      })
    }
    keepInViewport()
    window.addEventListener('resize', keepInViewport)
    return () => window.removeEventListener('resize', keepInViewport)
  }, [isOpen, mode])

  // Derived certification data
  const level = progress?.level || 'novice'
  const levelConfig = LEVEL_CONFIG[level] || LEVEL_CONFIG.novice
  const totalXp = progress?.total_xp || 0

  const [displayXp, setDisplayXp] = useState(totalXp)
  useEffect(() => {
    if (displayXp === totalXp) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setDisplayXp(totalXp); return }
    const diff = totalXp - displayXp
    const steps = Math.min(Math.abs(diff), 20)
    const increment = diff / steps
    let step = 0
    const timer = setInterval(() => {
      step++
      if (step >= steps) { setDisplayXp(totalXp); clearInterval(timer) }
      else { setDisplayXp(prev => Math.round(prev + increment)) }
    }, 50)
    return () => clearInterval(timer)
  }, [totalXp]) // eslint-disable-line react-hooks/exhaustive-deps

  const completedCount = useMemo(() => {
    if (!progress) return 0
    return MODULES.filter(module => progress.modules[module.id]?.completed).length
  }, [progress, MODULES])

  const nextLevel = LEVEL_THRESHOLDS.find(l => l.xp > totalXp)
  const prevLevel = [...LEVEL_THRESHOLDS].reverse().find(l => l.xp <= totalXp) || LEVEL_THRESHOLDS[0]
  const overallPct = MODULES.length ? (completedCount / MODULES.length) * 100 : 0

  const isModuleLocked = useModuleLock(progress, MODULES, course?.prerequisites)

  // Load exercise when active module changes
  useEffect(() => {
    if (!activeModule) { setExercise(null); return }
    let cancelled = false
    setExercise(null)
    getExercise(activeModule).then(value => { if (!cancelled) setExercise(value) }).catch(() => { if (!cancelled) setExercise(null) })
    return () => { cancelled = true }
  }, [activeModule, getExercise])

  const handleValidate = async (moduleId: string) => {
    if (pendingPanelActions.current.has('validate')) return
    pendingPanelActions.current.add('validate')
    setValidating(true); setValidationNotice({ scope: validationScope, state: 'checking' })
    // A bare try/finally re-throws on failure (e.g. a 5xx while the backend is
    // restarting), escaping as a global "Request failed" unhandled rejection.
    // Catch, notify, and keep the panel usable.
    let result: ValidationResult
    try {
      result = await validate(moduleId)
      if (currentValidationScope.current !== validationScope) {
        pendingPanelActions.current.delete('validate'); setValidating(false)
        return
      }
      setValidationResult({ scope: validationScope, result }); setValidationNotice(null)
    } catch {
      if (currentValidationScope.current === validationScope) {
        setValidationNotice({ scope: validationScope, state: 'unavailable' })
        toast('Could not validate the module right now. Please try again.', 'error')
      }
      pendingPanelActions.current.delete('validate'); setValidating(false)
      return
    }
    // Complete Module is hidden once a module is completed, and validate is
    // read-only, so a better result on a completed module was shown here but
    // never saved. Save the upgrade quietly — no celebration or module jump.
    const saved = progress?.modules[moduleId]
    try {
      if (result.passed && saved?.completed && result.stars > (saved.stars ?? 0)) {
        const upgrade = await complete(moduleId)
        if (currentValidationScope.current === validationScope) toast(`Saved: ${upgrade.stars} stars${upgrade.xp_earned ? ` (+${upgrade.xp_earned} XP)` : ''}`, 'success')
      }
    } catch {
      if (currentValidationScope.current === validationScope) toast('Could not save your new stars right now. Please check progress again.', 'error')
    } finally { pendingPanelActions.current.delete('validate'); setValidating(false) }
  }

  const handleComplete = async (moduleId: string, requestId?: string) => {
    if (pendingPanelActions.current.has('complete')) return
    pendingPanelActions.current.add('complete')
    setCompleting(true)
    try {
      const result = requestId ? await complete(moduleId, requestId) : await complete(moduleId)
      setCompletionResult(result)
      checkTierCompletion(moduleId)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'certification_execution_failed') {
        toast(error.message, 'error')
        await refresh()
      } else if (error instanceof ApiError && error.status === 400) {
        toast('Module not ready. Check the requirements below.', 'error')
        if (!course?.selected_outcome_completion) await handleValidate(moduleId)
      } else {
        toast(error instanceof ApiError && error.status === 409 ? error.message : 'Completion could not be confirmed. Resume the original request to finish or retrieve its saved result.', 'error')
      }
    } finally { pendingPanelActions.current.delete('complete'); setCompleting(false) }
  }

  const handleProvision = async (moduleId: string) => {
    if (pendingPanelActions.current.has('provision')) return
    pendingPanelActions.current.add('provision')
    setProvisioning(true)
    try {
      await provision(moduleId)
      // Invalidate document queries so the file browser shows the new files
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    } catch {
      // Bare try/finally re-throws; catch so a failed provision doesn't escape
      // as a global "Request failed" unhandled rejection.
      toast('Could not set up the exercise right now. Please try again.', 'error')
    } finally { pendingPanelActions.current.delete('provision'); setProvisioning(false) }
  }

  const handleSubmitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    if (pendingPanelActions.current.has('reflection')) return
    pendingPanelActions.current.add('reflection')
    setSubmittingAssessment(true)
    try {
      await submitAssessment(moduleId, answers)
    } catch {
      // Bare try/finally re-throws; catch so a failed submit doesn't escape as a
      // global "Request failed" unhandled rejection.
      toast('Could not submit your answers right now. Please try again.', 'error')
    } finally { pendingPanelActions.current.delete('reflection'); setSubmittingAssessment(false) }
  }

  const handleModuleClick = (moduleId: string) => {
    if (isModuleLocked(moduleId)) return
    setActiveModule(moduleId)
    setValidationResult(null)
  }

  const checkTierCompletion = useCallback((justCompletedModuleId: string) => {
    for (const tier of TIERS) {
      if (!tier.moduleIds.includes(justCompletedModuleId)) continue
      const allComplete = tier.moduleIds.every(id =>
        id === justCompletedModuleId ? true : progress?.modules[id]?.completed
      )
      if (allComplete) setTierCelebration({ tierName: tier.name, message: tier.celebration })
    }
  }, [progress, TIERS])

  const handleCelebrationDismiss = useCallback(() => {
    const completedModuleId = completionResult?.module_id
    setCompletionResult(null)
    setTierCelebration(null)
    if (completionResult?.certified) {
      setActiveModule(null)
      requestAnimationFrame(() => {
        const section = credentialSectionRef.current
        if (!section) return
        section.open = true
        const download = section.querySelector<HTMLButtonElement>('[data-cert-certificate] button')
        download?.focus()
      })
      return
    }
    if (completedModuleId) {
      const completedModule = MODULES.find(m => m.id === completedModuleId)
      if (completedModule) {
        const nextModule = MODULES.find(m => m.number === completedModule.number + 1)
        if (nextModule && !isModuleLocked(nextModule.id)) {
          setActiveModule(nextModule.id)
          toast(`Next up: ${nextModule.title}`, 'info')
          return
        }
      }
      if (!progress?.enrollment_id) localStorage.removeItem(`cert-lesson:${uid}:${completedModuleId}`)
    }
  }, [completionResult, isModuleLocked, toast, MODULES, setActiveModule, uid, progress?.enrollment_id])

  // Drag handlers for floating mode
  const handleDragStart = (e: React.PointerEvent) => {
    if (mode !== 'floating') return
    const panel = (e.currentTarget as HTMLElement).closest('[data-cert-panel]') as HTMLElement
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    dragRef.current = { startX: e.clientX, startY: e.clientY, panelX: rect.left, panelY: rect.top }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }

  const handleDragMove = (e: React.PointerEvent) => {
    if (!dragRef.current || mode !== 'floating') return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    const rect = panelRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = Math.max(0, Math.min(window.innerWidth - rect.width, dragRef.current.panelX + dx))
    const y = Math.max(0, Math.min(window.innerHeight - rect.height, dragRef.current.panelY + dy))
    setDragPos({ x, y })
  }

  const handleDragEnd = () => { dragRef.current = null }

  const activeModuleDef = MODULES.find(m => m.id === activeModule)
  const nextLessonModule = MODULES.find(module => !progress?.modules[module.id]?.completed && !isModuleLocked(module.id))

  if (!isOpen) return null

  // --- Container styles by mode ---
  const containerClass = cn(
    'fixed z-[9000] bg-white flex flex-col',
    mode === 'floating' && 'shadow-2xl border border-gray-200 cert-panel-enter',
    mode === 'fullscreen' && 'inset-0 cert-panel-enter',
    mode === 'docked-left' && 'top-[69px] left-0 bottom-0 border-r border-gray-200 cert-panel-dock-left',
    mode === 'docked-right' && 'top-[69px] right-0 bottom-0 border-l border-gray-200 cert-panel-dock-right',
    mode === 'docked-bottom' && 'left-0 right-0 bottom-0 border-t border-gray-200 cert-panel-dock-bottom',
  )

  const containerStyle: React.CSSProperties = {
    borderRadius: mode === 'floating' ? 'var(--ui-radius, 12px)' : undefined,
    ...(mode === 'floating'
      ? {
          width: 'min(540px, calc(100vw - 16px))',
          height: '80dvh',
          maxHeight: 740,
          top: dragPos ? dragPos.y : '50%',
          left: dragPos ? dragPos.x : '50%',
          transform: dragPos ? undefined : 'translate(-50%, -50%)',
        }
      : mode === 'docked-left'
        ? { width: 'min(440px, 100vw)' }
        : mode === 'docked-right'
          ? { width: 'min(440px, 100vw)' }
          : mode === 'docked-bottom'
            ? { height: 'min(360px, 100dvh)' }
            : {}),
  }

  // Panel content — two views: curriculum overview and module detail
  const panelContent = !progress ? (
    <div className="p-4 text-gray-500 text-sm">
      <p role="status" aria-live="polite">{loading ? 'Loading certification progress...' : 'Certification is unavailable. Refresh your progress to try again.'}</p>
      {!loading && <CourseHistory key={`course-history:${uid}`} />}
    </div>
  ) : activeModuleDef ? (
    // Navigation and course metadata scroll with the lesson so enlarged text
    // cannot consume the reading area with stacked fixed headers.
    <div>
      <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-gray-100 bg-gray-50/60 shrink-0">
        <button
          onClick={() => setActiveModule(null)}
          className="flex shrink-0 items-center gap-1 text-sm text-gray-500 hover:text-gray-900 transition-colors"
        >
          <ChevronLeft size={15} />
          <span>Curriculum</span>
        </button>
        <span aria-hidden="true" className="hidden text-gray-500 sm:inline">/</span>
        <span className="min-w-0 basis-full break-words text-sm text-gray-700 font-medium sm:basis-auto sm:flex-1">
          Module {activeModuleDef.number}: {activeModuleDef.title}
        </span>
      </div>
      <div className="p-[8px] sm:p-5 space-y-4">
        <ModuleDetail
          key={`${progress?.user_id}:${progress?.id}:${progress?.enrollment_id ?? 'legacy'}:${activeModuleDef.id}`}
          enrollmentId={progress?.enrollment_id}
          courseIdentity={course ?? undefined}
          progressRefreshPending={savedWritePendingRefresh}
          outcomeCompletionPending={completing || pendingCompletions?.some(item => item.module_id === activeModuleDef.id)}
          onCompleteOutcomes={course?.selected_outcome_completion === true ? async selection => {
            setCompleting(true)
            try {
              const result = await complete(activeModuleDef.id, undefined, selection)
              setCompletionResult(result)
              checkTierCompletion(activeModuleDef.id)
            } finally { setCompleting(false) }
          } : undefined}
          openChallengeRequest={assessmentEntry?.moduleId === activeModuleDef.id ? assessmentEntry.nonce : undefined}
          savedLessonId={progress?.modules[activeModuleDef.id]?.learning_position?.lesson_id}
          onSavePosition={progress?.enrollment_id ? lessonId => savePosition(activeModuleDef.id, lessonId) : undefined}
          onReloadPosition={refresh}
          onOpenWorkspace={async () => {
            if (onOpenWorkspace) await onOpenWorkspace()
            closePanel()
          }}
          onScenarioSaved={refresh}
          module={activeModuleDef}
          moduleProgress={progress?.modules[activeModuleDef.id] ? {
            completed: progress.modules[activeModuleDef.id].completed,
            stars: progress.modules[activeModuleDef.id].stars,
            attempts: progress.modules[activeModuleDef.id].attempts,
            provisioned_docs: progress.modules[activeModuleDef.id].provisioned_docs,
            self_assessment: progress.modules[activeModuleDef.id].self_assessment,
            scenario_attempt_id: progress.modules[activeModuleDef.id].scenario_attempt_id,
          } : null}
          onValidate={() => handleValidate(activeModuleDef.id)}
          onComplete={() => handleComplete(activeModuleDef.id)}
          onProvision={() => handleProvision(activeModuleDef.id)}
          onSubmitAssessment={(answers) => handleSubmitAssessment(activeModuleDef.id, answers)}
          onTabChange={handleStepChange}
          exercise={exercise}
          validating={validating}
          completing={completing}
          provisioning={provisioning}
          submittingAssessment={submittingAssessment}
        />
        {validationResult && (
          <ValidationResults result={validationResult} recheckState={validationRecheckState} recheckDisabled={validating} onRecheck={() => { void handleValidate(activeModuleDef.id) }} onDismiss={() => setValidationResult(null)} />
        )}
      </div>
    </div>
  ) : (
    // CURRICULUM VIEW — compact hero + journey map + level strip
    <div className="p-5 space-y-4">
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700" aria-label="Learn a useful task">
        <h3 className="font-semibold text-gray-900">Check a proposal requirement</h3>
        <p className="mt-1 text-xs text-gray-600">Optional walkthrough · work at your own pace</p>
        <ol className="my-3 list-decimal space-y-1 pl-5">
          <li>Open or upload a proposal document in Files.</li>
          <li>Ask: “What budget restrictions does this document state? Cite the passages.”</li>
          <li>Open each source reference and compare the answer with the original wording.</li>
        </ol>
        <p className="text-xs text-gray-600">If evidence is missing, check the source before using the answer. Export the conversation for a colleague to review.</p>
        <button type="button" onClick={closePanel} className="mt-3 rounded-md border border-gray-300 px-3 py-2 font-medium text-gray-900">Try in the workspace</button>
      </section>
      {nextLessonModule && <section className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-xs text-gray-600">Next in your optional course</p>
        <button type="button" onClick={() => handleModuleClick(nextLessonModule.id)} className="mt-2 text-left text-sm font-semibold text-gray-900 underline underline-offset-4">Continue: {nextLessonModule.title}</button>
        <p className="mt-1 text-xs text-gray-600">{progress?.enrollment_id ? 'Use Save this place in a lesson to resume here on any device.' : 'Your reading place is saved in this browser.'}</p>
      </section>}
      {course && <CourseBridgePath course={course} progress={progress} onAssess={moduleId => {
        if (isModuleLocked(moduleId)) return
        observeCertificationJourney('bridge_assessment_requested', course)
        setActiveModule(moduleId)
        setAssessmentEntry({ moduleId, nonce: Date.now() })
        setValidationResult(null)
      }} />}
      <details ref={credentialSectionRef}>
      <summary className="cursor-pointer text-sm font-medium text-gray-700">Course progress and credential</summary>
      {course && <CourseLearningPolicy course={course} />}
      <CourseHistory key={`course-history:${uid}`} />
      {progress?.enrollment_id && <CredentialHistory refreshKey={`${progress.enrollment_id}:${progress.certified}`} />}
      {progress?.enrollment_id && <UpgradeComparison key={progress.enrollment_id} enrollmentId={progress.enrollment_id} onRefreshCourse={refreshCourseChoice} />}
      {progress?.enrollment_id && <SavedCourseChoices key={`saved-choices:${progress.enrollment_id}`} enrollmentId={progress.enrollment_id} onRefreshCourse={refreshCourseChoice} />}
      {/* Compact hero */}
      {progress?.certified ? (
        <CertifiedBanner progress={progress} />
      ) : (
        <div
          className="flex items-center gap-4 p-4 bg-white border border-gray-200"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <div className="relative shrink-0">
            <ProgressRing percentage={overallPct} color={levelConfig.color} size={72} strokeWidth={6} />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-sm font-bold text-gray-900">{Math.round(overallPct)}%</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold uppercase tracking-wider" style={{ color: levelConfig.color }}>
                {levelConfig.label}
              </span>
            </div>
            <XPBar current={displayXp} nextThreshold={nextLevel?.xp ?? prevLevel.xp} prevThreshold={prevLevel.xp} nextLevel={nextLevel?.name} />
            <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
              <span><span className="font-semibold text-gray-900">{completedCount}</span> / {MODULES.length} modules</span>
              <span><span className="font-semibold text-gray-900">{displayXp}</span> XP toward this course</span>
            </div>
          </div>
        </div>
      )}
      {progress && Object.values(progress.modules).some(module => (module.xp_carried ?? 0) > 0) && <p className="mt-2 text-sm text-gray-700">Includes {Object.values(progress.modules).reduce((sum, module) => sum + (module.xp_carried ?? 0), 0)} XP carried from verified earlier credit; this is not a new XP reward.</p>}

      </details>

      {/* Journey Map */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Training Modules</h3>
        <JourneyMap
          modules={MODULES}
          tiers={TIERS}
          prerequisites={course?.prerequisites}
          progress={progress}
          activeModule={activeModule}
          isModuleLocked={isModuleLocked}
          onModuleClick={handleModuleClick}
        />
      </div>

      <XpMilestones levels={LEVEL_THRESHOLDS} totalXp={totalXp} />
    </div>
  )

  return createPortal(
    <>
      {/* Subtle backdrop for floating mode — pointer-events-none so the app stays interactive */}
      {mode === 'floating' && (
        <div
          className="fixed inset-0 z-[8999] bg-black/5 cert-fade-in pointer-events-none"
        />
      )}

      <FocusTrap active={mode === 'fullscreen'} focusTrapOptions={{ escapeDeactivates: false, delayInitialFocus: false, initialFocus: () => panelRef.current!, fallbackFocus: () => panelRef.current!, returnFocusOnDeactivate: false }}>
      <div ref={panelRef} tabIndex={-1} role={mode === 'fullscreen' ? 'dialog' : 'region'} aria-modal={mode === 'fullscreen' ? true : undefined} aria-label="Learning and certification" data-cert-panel className={containerClass} style={containerStyle} onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); closePanel() } }}>
        {/* Title bar */}
        <div
          className={cn(
            'flex flex-wrap items-center gap-1 px-2 py-2.5 border-b border-gray-200 shrink-0 select-none sm:gap-2 sm:px-4',
            mode === 'floating' && 'cursor-grab active:cursor-grabbing',
          )}
          style={mode === 'floating' ? { borderRadius: 'var(--ui-radius, 12px) var(--ui-radius, 12px) 0 0' } : undefined}
          onPointerDown={handleDragStart}
          onPointerMove={handleDragMove}
          onPointerUp={handleDragEnd}
          onPointerCancel={handleDragEnd}
        >
          {mode === 'floating' && <GripHorizontal size={14} className="text-gray-500 shrink-0" />}
          <Award size={16} aria-hidden="true" className="text-highlight shrink-0" style={{ color: 'var(--highlight-on-light, #806600)' }} />
          <span className="min-w-0 flex-1 text-sm font-bold text-gray-900 [overflow-wrap:anywhere]">Certification</span>

          <button type="button" onPointerDown={e => e.stopPropagation()} onClick={closePanel} title="Return to workspace" aria-label="Return to workspace" className="p-1.5 rounded-md text-gray-500 hover:text-gray-600 hover:bg-gray-50 ml-1">
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        <div ref={moduleScrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-2">
            <label className="grid min-w-0 flex-1 gap-1 text-xs text-gray-600 sm:flex sm:items-center">
              <span className="sm:sr-only">Learning panel position</span>
              <select value={mode} onChange={event => setMode(event.target.value as PanelMode)} className="min-w-0 w-full rounded-md border border-gray-300 bg-white p-1.5 text-gray-800 sm:w-auto">
                {PANEL_POSITIONS.map(position => <option key={position.mode} value={position.mode}>{position.label}</option>)}
              </select>
            </label>
            {/* The second-monitor ask: an explicit pop-out, not a mode the
                user has to discover by opening another browser tab herself. */}
            <button
              type="button"
              onClick={() => {
                window.open('/certification?panel=fullscreen', '_blank', 'noopener,width=1080,height=860')
                closePanel()
              }}
              title={'Open in a new window \u2014 put the course on another monitor while you work here'}
              aria-label="Open certification in a new window"
              className="p-1.5 rounded-md text-gray-500 hover:text-gray-600 hover:bg-gray-50"
            >
              <ExternalLink size={14} aria-hidden="true" />
            </button>
          </div>

        <CertificationRefreshNotice />
        <CourseSelectionNotice key={`selection:${uid}`} refreshKey={selectionRefresh} enrollmentId={progress?.enrollment_id} onRefreshCourse={refreshCourseChoice} />
        {course && <p className="border-b border-gray-100 px-4 py-2 text-xs font-medium text-gray-700" aria-label="Your course">{course.course_title}</p>}
        <CompletionResumeNotice pending={pendingCompletions} modules={MODULES} course={course ?? progress} busy={completing || loading} onOpen={setActiveModule} onRetry={handleComplete} onRefresh={refresh} onHelp={closePanel} />
        {/* Panel body */}
        {panelContent}
        </div>
      </div>
      </FocusTrap>

      {/* Celebration overlay — always full-screen via portal */}
      {completionResult && (
        <CelebrationOverlay
          result={completionResult}
          onDismiss={handleCelebrationDismiss}
          tierCelebration={tierCelebration}
        />
      )}
    </>,
    document.body,
  )
}
