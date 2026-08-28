import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Award,
  Cog,
  ShieldCheck,
  Star,
  Target,
  X,
  Zap,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useCertification } from '../hooks/useCertification'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import { cn } from '../lib/cn'
import type { ValidationResult, CompletionResult, ValidationCheck, CertExercise } from '../types/certification'

// Components
import { CertifiedBanner } from '../components/certification/CertifiedBanner'
import { CelebrationOverlay } from '../components/certification/CelebrationOverlay'
import { ModuleDetail } from '../components/certification/ModuleDetail'
import { useQueryClient } from '@tanstack/react-query'
import { JourneyMap } from '../components/certification/JourneyMap'
import { LEVEL_CONFIG, LEVEL_THRESHOLDS, TOTAL_XP, TIERS } from '../components/certification/constants'
import { useModuleLock } from '../components/certification/useModuleLock'
import { MODULES } from '../components/certification/modules'

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

function ValidationResults({ result, onDismiss }: { result: ValidationResult; onDismiss: () => void }) {
  return (
    <div
      role={result.passed ? 'status' : 'alert'}
      aria-live={result.passed ? 'polite' : 'assertive'}
      className={cn(
        'border-2 p-4 cert-slide-in',
        result.passed ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50',
      )}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {result.passed
            ? <ShieldCheck size={18} className="text-green-600" />
            : <Target size={18} className="text-amber-600" />
          }
          <span className={cn('font-semibold text-sm', result.passed ? 'text-green-800' : 'text-amber-800')}>
            {result.passed ? 'All checks passed!' : 'Some objectives remaining'}
          </span>
          {result.passed && (
            <div className="flex gap-0.5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Star
                  key={i}
                  size={14}
                  className={cn(
                    'transition-all duration-300',
                    i < result.stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300',
                  )}
                />
              ))}
            </div>
          )}
        </div>
        <button type="button" onClick={onDismiss} aria-label="Dismiss results" className="text-gray-400 hover:text-gray-600">
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="space-y-1.5">
        {result.checks.map((check: ValidationCheck, i: number) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            {check.passed
              ? <span className="text-green-600 shrink-0">&#10003;</span>
              : <X size={14} className="text-red-500 shrink-0" />
            }
            <span className={check.passed ? 'text-green-800' : 'text-red-700'}>{check.name}</span>
            <span className="text-gray-500 text-xs">{check.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Certification() {
  const { progress, loading, validate, complete, provision, getExercise, submitAssessment } = useCertification()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const uid = user?.user_id || ''
  const [activeModule, setActiveModuleState] = useState<string | null>(() => {
    try { return localStorage.getItem(`cert-active-module:${uid}`) } catch { return null }
  })
  const setActiveModule = useCallback((id: string | null) => {
    setActiveModuleState(id)
    try { if (id) localStorage.setItem(`cert-active-module:${uid}`, id); else localStorage.removeItem(`cert-active-module:${uid}`) } catch {}
  }, [uid])
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [completionResult, setCompletionResult] = useState<CompletionResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [provisioning, setProvisioning] = useState(false)
  const [submittingAssessment, setSubmittingAssessment] = useState(false)
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
    return Object.values(progress.modules).filter(m => m.completed).length
  }, [progress])

  // Find next level threshold
  const currentLevelIdx = LEVEL_THRESHOLDS.findIndex(l => l.name === level)
  const nextLevel = LEVEL_THRESHOLDS[currentLevelIdx + 1] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1]
  const prevLevel = LEVEL_THRESHOLDS[currentLevelIdx] || LEVEL_THRESHOLDS[0]

  const overallPct = (totalXp / TOTAL_XP) * 100

  const isModuleLocked = useModuleLock(progress)

  // Load exercise when active module changes
  useEffect(() => {
    if (!activeModule) {
      setExercise(null)
      return
    }
    getExercise(activeModule).then(setExercise).catch(() => setExercise(null))
  }, [activeModule, getExercise])

  const handleValidate = async (moduleId: string) => {
    setValidating(true)
    setValidationResult(null)
    try {
      const result = await validate(moduleId)
      setValidationResult(result)
    } catch {
      // A bare try/finally re-throws on failure (e.g. a 5xx while the backend is
      // restarting), escaping as a global "Request failed" unhandled rejection.
      toast('Could not validate the module right now. Please try again.', 'error')
    } finally {
      setValidating(false)
    }
  }

  const handleComplete = async (moduleId: string) => {
    setCompleting(true)
    try {
      const result = await complete(moduleId)
      setCompletionResult(result)
      // Check if a tier was just completed
      checkTierCompletion(moduleId)
    } catch {
      // Validation failed - show what's missing
      toast('Module not ready. Check the requirements below.', 'error')
      await handleValidate(moduleId)
    } finally {
      setCompleting(false)
    }
  }

  const handleProvision = async (moduleId: string) => {
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
      setProvisioning(false)
    }
  }

  const handleSubmitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    setSubmittingAssessment(true)
    try {
      await submitAssessment(moduleId, answers)
    } catch {
      // Bare try/finally re-throws; catch so a failed submit doesn't escape as a
      // global "Request failed" unhandled rejection.
      toast('Could not submit your answers right now. Please try again.', 'error')
    } finally {
      setSubmittingAssessment(false)
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
  }, [progress])

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
      localStorage.removeItem(`cert-lesson:${uid}:${completedModuleId}`)
    }
  }, [completionResult, isModuleLocked, toast])

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

        {/* Hero Section */}
        {progress?.certified ? (
          <CertifiedBanner />
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
                Complete all 11 modules to earn your official certification
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
                  <span className="text-gray-500">/ 11 modules</span>
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
              module={activeModuleDef}
              moduleProgress={progress?.modules[activeModuleDef.id] ? {
                completed: progress.modules[activeModuleDef.id].completed,
                stars: progress.modules[activeModuleDef.id].stars,
                attempts: progress.modules[activeModuleDef.id].attempts,
                provisioned_docs: progress.modules[activeModuleDef.id].provisioned_docs,
                self_assessment: progress.modules[activeModuleDef.id].self_assessment,
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
              <ValidationResults result={validationResult} onDismiss={() => setValidationResult(null)} />
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
