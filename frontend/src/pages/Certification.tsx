import { ValidationResults } from '../components/certification/ValidationResults'
import { CompletionResumeNotice } from '../components/certification/CompletionResumeNotice'
import { CourseSelectionNotice } from '../components/certification/CourseSelectionNotice'
import { CourseLearningPolicy } from '../components/certification/CourseLearningPolicy'
import { ApiError } from '../api/client'
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Award,
  Cog,
  Zap,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useCertification } from '../hooks/useCertification'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import { cn } from '../lib/cn'
import type { ValidationResult, CompletionResult, CertExercise } from '../types/certification'

// Components
import { CertifiedBanner } from '../components/certification/CertifiedBanner'
import { CredentialHistory } from '../components/certification/CredentialHistory'
import { CelebrationOverlay } from '../components/certification/CelebrationOverlay'
import { ModuleDetail } from '../components/certification/ModuleDetail'
import { useQueryClient } from '@tanstack/react-query'
import { JourneyMap } from '../components/certification/JourneyMap'
import { LEVEL_CONFIG, LEVEL_THRESHOLDS as LEGACY_LEVELS, TOTAL_XP as LEGACY_TOTAL_XP, TIERS as LEGACY_TIERS } from '../components/certification/constants'
import { useModuleLock } from '../components/certification/useModuleLock'
import { MODULES as LEGACY_MODULES } from '../components/certification/modules'

// ---------------------------------------------------------------------------
// Progress ring component
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
    const timer = setTimeout(() => setAnimatedOffset(offset), 100)
    return () => clearTimeout(timer)
  }, [offset])

  return (
    <svg width={size} height={size} className="cert-ring-spin">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={animatedOffset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// XP bar
// ---------------------------------------------------------------------------

function XPBar({ current, nextThreshold, prevThreshold, nextLevel }: {
  current: number
  nextThreshold: number
  prevThreshold: number
  nextLevel: string
}) {
  const range = nextThreshold - prevThreshold
  const progress = Math.min(((current - prevThreshold) / range) * 100, 100)

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-gray-500">{current} XP</span>
        <span className="text-xs text-gray-500">
          {nextThreshold - current} XP to {LEVEL_CONFIG[nextLevel]?.label || 'Max'}
        </span>
      </div>
      <div className="h-2.5 bg-gray-200 overflow-hidden" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
        <div
          className="h-full cert-xp-glow"
          style={{
            width: `${progress}%`,
            background: `linear-gradient(90deg, var(--highlight-color), var(--highlight-complement))`,
            borderRadius: 'var(--ui-radius, 12px)',
            transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Validation results
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Certification() {
  const { progress, course, pendingCompletions, loading, validate, complete, provision, getExercise, submitAssessment, savePosition, refresh } = useCertification()
  const MODULES = course?.modules ?? LEGACY_MODULES
  const LEVEL_THRESHOLDS = course?.levels ?? LEGACY_LEVELS
  const TOTAL_XP = course?.maximum_xp ?? LEGACY_TOTAL_XP
  const TIERS = course?.tiers ?? LEGACY_TIERS
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const uid = user?.user_id || ''
  const [activeModule, setActiveModuleState] = useState<string | null>(() => {
    try { return localStorage.getItem(`cert-active-module:${uid}`) } catch { return null }
  })
  useEffect(() => {
    if (progress?.enrollment_id) return
    try { setActiveModuleState(localStorage.getItem(`cert-active-module:${uid}`)) } catch { setActiveModuleState(null) }
  }, [uid, progress?.enrollment_id])
  const restoredEnrollment = useRef<string | null>(null)
  useEffect(() => {
    if (!progress?.enrollment_id || restoredEnrollment.current === progress.enrollment_id) return
    restoredEnrollment.current = progress.enrollment_id
    setActiveModuleState(progress.learning_position?.module_id ?? null)
  }, [progress])
  const setActiveModule = useCallback((id: string | null) => {
    setActiveModuleState(id)
    try { if (id) localStorage.setItem(`cert-active-module:${uid}`, id); else localStorage.removeItem(`cert-active-module:${uid}`) } catch {}
  }, [uid])
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
  const detailRef = useRef<HTMLDivElement>(null)

  const level = progress?.level || 'novice'
  const levelConfig = LEVEL_CONFIG[level] || LEVEL_CONFIG.novice
  const totalXp = progress?.total_xp || 0

  // XP count-up animation
  const [displayXp, setDisplayXp] = useState(totalXp)
  useEffect(() => {
    if (displayXp === totalXp) return
    const diff = totalXp - displayXp
    const steps = Math.min(Math.abs(diff), 20)
    const increment = diff / steps
    let step = 0
    const timer = setInterval(() => {
      step++
      if (step >= steps) {
        setDisplayXp(totalXp)
        clearInterval(timer)
      } else {
        setDisplayXp(prev => Math.round(prev + increment))
      }
    }, 50)
    return () => clearInterval(timer)
  }, [totalXp]) // eslint-disable-line react-hooks/exhaustive-deps
  const completedCount = useMemo(() => {
    if (!progress) return 0
    return MODULES.filter(module => progress.modules[module.id]?.completed).length
  }, [progress, MODULES])

  // Find next level threshold
  const currentLevelIdx = LEVEL_THRESHOLDS.findIndex(l => l.name === level)
  const nextLevel = LEVEL_THRESHOLDS[currentLevelIdx + 1] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1]
  const prevLevel = LEVEL_THRESHOLDS[currentLevelIdx] || LEVEL_THRESHOLDS[0]

  const overallPct = Math.min(100, Math.max(0, (totalXp / TOTAL_XP) * 100))

  const isModuleLocked = useModuleLock(progress, MODULES, course?.prerequisites)

  // Load exercise when active module changes
  useEffect(() => {
    if (!activeModule) {
      setExercise(null)
      return
    }
    let cancelled = false
    setExercise(null)
    getExercise(activeModule).then(value => { if (!cancelled) setExercise(value) }).catch(() => { if (!cancelled) setExercise(null) })
    return () => { cancelled = true }
  }, [activeModule, getExercise])

  const handleValidate = async (moduleId: string) => {
    if (pendingPanelActions.current.has('validate')) return
    pendingPanelActions.current.add('validate')
    setValidating(true)
    setValidationNotice({ scope: validationScope, state: 'checking' })
    try {
      const result = await validate(moduleId)
      if (currentValidationScope.current !== validationScope) {
        pendingPanelActions.current.delete('validate'); setValidating(false)
        return
      }
      setValidationResult({ scope: validationScope, result }); setValidationNotice(null)
    } catch {
      // A bare try/finally re-throws on failure (e.g. a 5xx while the backend is
      // restarting), escaping as a global "Request failed" unhandled rejection.
      if (currentValidationScope.current === validationScope) {
        setValidationNotice({ scope: validationScope, state: 'unavailable' })
        toast('Could not validate the module right now. Please try again.', 'error')
      }
    } finally {
      pendingPanelActions.current.delete('validate'); setValidating(false)
    }
  }

  const handleComplete = async (moduleId: string, requestId?: string) => {
    if (pendingPanelActions.current.has('complete')) return
    pendingPanelActions.current.add('complete')
    setCompleting(true)
    try {
      const result = requestId ? await complete(moduleId, requestId) : await complete(moduleId)
      setCompletionResult(result)
      // Check if a tier was just completed
      checkTierCompletion(moduleId)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'certification_execution_failed') {
        toast(error.message, 'error')
        await refresh()
      } else if (error instanceof ApiError && error.status === 400) {
        toast('Module not ready. Check the requirements below.', 'error')
        await handleValidate(moduleId)
      } else {
        toast(error instanceof ApiError && error.status === 409 ? error.message : 'Completion could not be confirmed. Resume the original request to finish or retrieve its saved result.', 'error')
      }
    } finally {
      pendingPanelActions.current.delete('complete'); setCompleting(false)
    }
  }

  const handleProvision = async (moduleId: string) => {
    if (pendingPanelActions.current.has('provision')) return
    pendingPanelActions.current.add('provision')
    setProvisioning(true)
    try {
      await provision(moduleId)
      // Invalidate document queries so workspace shows the new files without a hard refresh
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    } catch {
      // Bare try/finally re-throws; catch so a failed provision doesn't escape
      // as a global "Request failed" unhandled rejection.
      toast('Could not set up the exercise right now. Please try again.', 'error')
    } finally {
      pendingPanelActions.current.delete('provision'); setProvisioning(false)
    }
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
    } finally {
      pendingPanelActions.current.delete('reflection'); setSubmittingAssessment(false)
    }
  }

  const handleModuleClick = (moduleId: string) => {
    if (isModuleLocked(moduleId)) return
    setActiveModule(activeModule === moduleId ? null : moduleId)
    setValidationResult(null)
    // Scroll to detail after render
    setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
  }

  // Check if completing this module finishes a tier
  const [tierCelebration, setTierCelebration] = useState<{ tierName: string; message: string } | null>(null)

  const checkTierCompletion = useCallback((justCompletedModuleId: string) => {
    for (const tier of TIERS) {
      if (!tier.moduleIds.includes(justCompletedModuleId)) continue
      const allComplete = tier.moduleIds.every(id => {
        if (id === justCompletedModuleId) return true // Just completed
        return progress?.modules[id]?.completed
      })
      if (allComplete) {
        setTierCelebration({ tierName: tier.name, message: tier.celebration })
      }
    }
  }, [progress, TIERS])

  // Auto-navigate to next module after celebration dismissal
  const handleCelebrationDismiss = useCallback(() => {
    const completedModuleId = completionResult?.module_id
    setCompletionResult(null)
    setTierCelebration(null)

    if (completedModuleId) {
      const completedModule = MODULES.find(m => m.id === completedModuleId)
      if (completedModule) {
        const nextModule = MODULES.find(m => m.number === completedModule.number + 1)
        if (nextModule && !isModuleLocked(nextModule.id)) {
          // Auto-navigate to next module
          setActiveModule(nextModule.id)
          toast(`Next up: ${nextModule.title}`, 'info')
          setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
          return
        }
      }
    }
    // Clear lesson localStorage for completed module
    if (completedModuleId) {
      if (!progress?.enrollment_id) localStorage.removeItem(`cert-lesson:${uid}:${completedModuleId}`)
    }
  }, [completionResult, isModuleLocked, toast, MODULES, setActiveModule, uid, progress?.enrollment_id])

  if (loading && !progress) {
    return (
      <PageLayout>
        <div className="p-6 max-w-5xl mx-auto">
          <div role="status" aria-live="polite" className="text-gray-500 text-sm">Loading certification progress...</div>
        </div>
      </PageLayout>
    )
  }

  const activeModuleDef = MODULES.find(m => m.id === activeModule)

  return (
    <PageLayout>
      <div className="p-6 max-w-5xl mx-auto space-y-8">
        {course && <p className="text-sm font-medium text-gray-700" aria-label="Your course">{course.course_title}</p>}

        <CourseSelectionNotice key={`selection:${uid}`} enrollmentId={progress?.enrollment_id} onRefreshCourse={refresh} />
        {course && <CourseLearningPolicy course={course} />}
        <CompletionResumeNotice pending={pendingCompletions} modules={MODULES} course={course ?? progress} busy={completing || loading} onOpen={setActiveModule} onRetry={handleComplete} onRefresh={refresh} />
        {/* Hero Section */}
        {progress?.enrollment_id && <CredentialHistory refreshKey={`${progress.enrollment_id}:${progress.certified}`} />}
        {progress?.certified ? (
          <CertifiedBanner progress={progress} />
        ) : (
          <div
            className="flex flex-col sm:flex-row items-center gap-8 p-6 bg-white border border-gray-200"
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            {/* Progress Ring */}
            <div className="relative shrink-0">
              <ProgressRing percentage={overallPct} color={levelConfig.color} />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-gray-900">{Math.round(overallPct)}%</span>
                <span
                  className="text-xs font-bold uppercase tracking-wider"
                  style={{ color: levelConfig.color }}
                >
                  {levelConfig.label}
                </span>
              </div>
            </div>

            {/* Stats */}
            <div className="flex-1 w-full">
              <h1 className="text-2xl font-bold text-gray-900 mb-1">
                Vandal Workflow Architect
              </h1>
              <p className="text-sm text-gray-500 mb-2">
                Complete all {MODULES.length} modules to earn your official certification
              </p>
              <div
                className="flex items-center gap-2 px-3 py-2 mb-4 border border-yellow-200 bg-yellow-50/60"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <Award size={16} className="text-yellow-600 shrink-0" />
                <p className="text-xs text-yellow-800">
                  <span className="font-bold">Vandal Workflow Architect (VWA)</span>: a University of Idaho credential recognizing your ability to design, build, and deploy AI-powered document workflows for research administration.
                </p>
              </div>

              {/* XP bar */}
              <XPBar
                current={totalXp}
                nextThreshold={nextLevel.xp}
                prevThreshold={prevLevel.xp}
                nextLevel={nextLevel.name}
              />

              {/* Stat pills */}
              <div className="flex flex-wrap gap-3 mt-4">
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-200 text-sm"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Award size={14} className="text-highlight-on-light" style={{ color: 'var(--highlight-on-light, #806600)' }} />
                  <span className="font-semibold text-gray-900">{completedCount}</span>
                  <span className="text-gray-500">/ {MODULES.length} modules</span>
                </div>
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-200 text-sm"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Zap size={14} className="text-highlight-on-light" style={{ color: 'var(--highlight-on-light, #806600)' }} />
                  <span className="font-semibold text-gray-900">{displayXp}</span>
                  <span className="text-gray-500">/ {TOTAL_XP} XP</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Journey Map (replaces flat module grid) */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Training Modules</h2>
          <JourneyMap
            modules={MODULES}
          tiers={TIERS}
            progress={progress}
            activeModule={activeModule}
            isModuleLocked={isModuleLocked}
            onModuleClick={handleModuleClick}
          />
        </div>

        {/* Active Module Detail */}
        {activeModuleDef && (
          <div ref={detailRef} className="space-y-4">
            <ModuleDetail
              key={`${progress?.enrollment_id ?? 'legacy'}:${activeModuleDef.id}`}
              enrollmentId={progress?.enrollment_id}
              savedLessonId={progress?.modules[activeModuleDef.id]?.learning_position?.lesson_id}
              onSavePosition={progress?.enrollment_id ? lessonId => savePosition(activeModuleDef.id, lessonId) : undefined}
              onReloadPosition={refresh}
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
        )}

        {/* Level Map */}
        <div
          className="p-5 bg-white border border-gray-200"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-1.5">
            <Cog size={14} />
            Level Progression
          </h3>
          <div className="flex items-center gap-1">
            {LEVEL_THRESHOLDS.map((lvl, i) => {
              const config = LEVEL_CONFIG[lvl.name]
              const reached = totalXp >= lvl.xp
              const isCurrent = level === lvl.name
              return (
                <div key={lvl.name} className="flex-1 flex flex-col items-center">
                  <div
                    className={cn(
                      'w-full h-2 transition-all duration-500',
                      i === 0 && 'rounded-l-full',
                      i === LEVEL_THRESHOLDS.length - 1 && 'rounded-r-full',
                    )}
                    style={{
                      background: reached ? config.color : '#e5e7eb',
                    }}
                  />
                  <div
                    className={cn(
                      'mt-2 text-[10px] font-medium text-center transition-all',
                      isCurrent ? 'font-bold' : reached ? '' : 'text-gray-400',
                    )}
                    style={reached ? { color: config.color } : undefined}
                  >
                    {config.label}
                  </div>
                  {isCurrent && (
                    <div
                      className="w-1.5 h-1.5 rounded-full mt-0.5"
                      style={{ background: config.color }}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Celebration overlay */}
      {completionResult && (
        <CelebrationOverlay
          result={completionResult}
          onDismiss={handleCelebrationDismiss}
          tierCelebration={tierCelebration}
        />
      )}
    </PageLayout>
  )
}
