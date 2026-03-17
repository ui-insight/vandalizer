import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  Award,
  Cog,
  Flame,
  GripHorizontal,
  Maximize2,
  Minimize2,
  PanelBottom,
  PanelLeft,
  PanelRight,
  ShieldCheck,
  Star,
  Target,
  X,
  Zap,
} from 'lucide-react'
import { useCertificationPanel, type PanelMode } from '../../contexts/CertificationPanelContext'
import { useCertification } from '../../hooks/useCertification'
import { useToast } from '../../contexts/ToastContext'
import { cn } from '../../lib/cn'
import type { ModuleDefinition, ValidationResult, CompletionResult, ValidationCheck, CertExercise } from '../../types/certification'
import { LEVEL_CONFIG, LEVEL_THRESHOLDS, TOTAL_XP, TIERS } from './constants'
import { CertifiedBanner } from './CertifiedBanner'
import { CelebrationOverlay } from './CelebrationOverlay'
import { ModuleDetail } from './ModuleDetail'
import { JourneyMap } from './JourneyMap'

// ---------------------------------------------------------------------------
// MODULES — inline here since they live in the page file, not in constants
// We re-import them lazily from the page module to avoid duplication
// ---------------------------------------------------------------------------
// The MODULES array is large and lives in Certification.tsx. Rather than
// duplicating, we import dynamically. For the panel, we need them at render
// time, so we'll pass them from the Certification page or load eagerly.
// For now, we import directly from the page file.
import { MODULES } from '../../pages/Certification'

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
    const timer = setTimeout(() => setAnimatedOffset(offset), 100)
    return () => clearTimeout(timer)
  }, [offset])

  return (
    <svg width={size} height={size} className="cert-ring-spin">
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
  current: number; nextThreshold: number; prevThreshold: number; nextLevel: string
}) {
  const range = nextThreshold - prevThreshold
  const progress = Math.min(((current - prevThreshold) / range) * 100, 100)
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-gray-500">{current} XP</span>
        <span className="text-xs text-gray-400">
          {nextThreshold - current} XP to {LEVEL_CONFIG[nextLevel]?.label || 'Max'}
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

function ValidationResults({ result, onDismiss }: { result: ValidationResult; onDismiss: () => void }) {
  return (
    <div
      className={cn('border-2 p-4 cert-slide-in', result.passed ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50')}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {result.passed ? <ShieldCheck size={18} className="text-green-600" /> : <Target size={18} className="text-amber-600" />}
          <span className={cn('font-semibold text-sm', result.passed ? 'text-green-800' : 'text-amber-800')}>
            {result.passed ? 'All checks passed!' : 'Some objectives remaining'}
          </span>
          {result.passed && (
            <div className="flex gap-0.5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Star key={i} size={14} className={cn('transition-all duration-300', i < result.stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300')} />
              ))}
            </div>
          )}
        </div>
        <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
      </div>
      <div className="space-y-1.5">
        {result.checks.map((check: ValidationCheck, i: number) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            {check.passed ? <span className="text-green-600 shrink-0">&#10003;</span> : <X size={14} className="text-red-500 shrink-0" />}
            <span className={check.passed ? 'text-green-800' : 'text-red-700'}>{check.name}</span>
            <span className="text-gray-500 text-xs">&mdash; {check.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mode toggle buttons
// ---------------------------------------------------------------------------

const MODE_ICONS: { mode: PanelMode; icon: typeof Maximize2; label: string }[] = [
  { mode: 'floating', icon: Maximize2, label: 'Float' },
  { mode: 'docked-left', icon: PanelLeft, label: 'Dock left' },
  { mode: 'docked-right', icon: PanelRight, label: 'Dock right' },
  { mode: 'docked-bottom', icon: PanelBottom, label: 'Dock bottom' },
  { mode: 'collapsed', icon: Minimize2, label: 'Collapse' },
]

// ---------------------------------------------------------------------------
// Main panel component
// ---------------------------------------------------------------------------

export function CertificationPanel() {
  const { isOpen, mode, closePanel, setMode } = useCertificationPanel()
  const { progress, loading, validate, complete, provision, getExercise, submitAssessment } = useCertification()
  const { toast } = useToast()

  // Module interaction state
  const [activeModule, setActiveModule] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)
  const [completionResult, setCompletionResult] = useState<CompletionResult | null>(null)
  const [validating, setValidating] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [provisioning, setProvisioning] = useState(false)
  const [submittingAssessment, setSubmittingAssessment] = useState(false)
  const [exercise, setExercise] = useState<CertExercise | null>(null)
  const [tierCelebration, setTierCelebration] = useState<{ tierName: string; message: string } | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  // Drag state for floating mode
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null)
  const dragRef = useRef<{ startX: number; startY: number; panelX: number; panelY: number } | null>(null)

  // Derived certification data
  const level = progress?.level || 'novice'
  const levelConfig = LEVEL_CONFIG[level] || LEVEL_CONFIG.novice
  const totalXp = progress?.total_xp || 0

  const [displayXp, setDisplayXp] = useState(totalXp)
  useEffect(() => {
    if (displayXp === totalXp) return
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
    return Object.values(progress.modules).filter(m => m.completed).length
  }, [progress])

  const currentLevelIdx = LEVEL_THRESHOLDS.findIndex(l => l.name === level)
  const nextLevel = LEVEL_THRESHOLDS[currentLevelIdx + 1] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1]
  const prevLevel = LEVEL_THRESHOLDS[currentLevelIdx] || LEVEL_THRESHOLDS[0]
  const overallPct = (totalXp / TOTAL_XP) * 100

  const isModuleLocked = useCallback((moduleId: string): boolean => {
    const module = MODULES.find(m => m.id === moduleId)
    if (!module) return true
    if (module.number === 0) return false
    const prevModule = MODULES.find(m => m.number === module.number - 1)
    if (!prevModule) return false
    return !progress?.modules[prevModule.id]?.completed
  }, [progress])

  // Load exercise when active module changes
  useEffect(() => {
    if (!activeModule) { setExercise(null); return }
    getExercise(activeModule).then(setExercise).catch(() => setExercise(null))
  }, [activeModule, getExercise])

  const handleValidate = async (moduleId: string) => {
    setValidating(true); setValidationResult(null)
    try { setValidationResult(await validate(moduleId)) } finally { setValidating(false) }
  }

  const handleComplete = async (moduleId: string) => {
    setCompleting(true)
    try {
      const result = await complete(moduleId)
      setCompletionResult(result)
      checkTierCompletion(moduleId)
    } catch {
      toast('Module not ready — check the requirements below', 'error')
      await handleValidate(moduleId)
    } finally { setCompleting(false) }
  }

  const handleProvision = async (moduleId: string) => {
    setProvisioning(true)
    try { await provision(moduleId) } finally { setProvisioning(false) }
  }

  const handleSubmitAssessment = async (moduleId: string, answers: Record<string, string>) => {
    setSubmittingAssessment(true)
    try { await submitAssessment(moduleId, answers) } finally { setSubmittingAssessment(false) }
  }

  const handleModuleClick = (moduleId: string) => {
    if (isModuleLocked(moduleId)) return
    setActiveModule(activeModule === moduleId ? null : moduleId)
    setValidationResult(null)
    setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
  }

  const checkTierCompletion = useCallback((justCompletedModuleId: string) => {
    for (const tier of TIERS) {
      if (!tier.moduleIds.includes(justCompletedModuleId)) continue
      const allComplete = tier.moduleIds.every(id =>
        id === justCompletedModuleId ? true : progress?.modules[id]?.completed
      )
      if (allComplete) setTierCelebration({ tierName: tier.name, message: tier.celebration })
    }
  }, [progress])

  const handleCelebrationDismiss = useCallback(() => {
    const completedModuleId = completionResult?.module_id
    setCompletionResult(null)
    setTierCelebration(null)
    if (completedModuleId) {
      const completedModule = MODULES.find(m => m.id === completedModuleId)
      if (completedModule) {
        const nextModule = MODULES.find(m => m.number === completedModule.number + 1)
        if (nextModule && !isModuleLocked(nextModule.id)) {
          setActiveModule(nextModule.id)
          toast(`Next up: ${nextModule.title}`, 'info')
          setTimeout(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100)
          return
        }
      }
      localStorage.removeItem(`cert-lesson-${completedModuleId}`)
    }
  }, [completionResult, isModuleLocked, toast])

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
    const x = Math.max(0, Math.min(window.innerWidth - 200, dragRef.current.panelX + dx))
    const y = Math.max(0, Math.min(window.innerHeight - 100, dragRef.current.panelY + dy))
    setDragPos({ x, y })
  }

  const handleDragEnd = () => { dragRef.current = null }

  // Don't render anything when closed
  if (!isOpen) return null

  const activeModuleDef = MODULES.find(m => m.id === activeModule)

  // --- Collapsed pill ---
  if (mode === 'collapsed') {
    return createPortal(
      <div
        className="fixed bottom-4 right-4 z-[9000] flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 shadow-lg cursor-pointer hover:shadow-xl transition-all cert-panel-collapse"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        onClick={() => setMode('floating')}
      >
        <Award size={16} className="text-highlight" style={{ color: 'var(--highlight-color)' }} />
        <span className="text-sm font-semibold text-gray-900">{levelConfig.label}</span>
        <span className="text-xs text-gray-400">{displayXp} XP</span>
      </div>,
      document.body,
    )
  }

  // --- Container styles by mode ---
  const containerClass = cn(
    'fixed z-[9000] bg-white flex flex-col',
    mode === 'floating' && 'shadow-2xl border border-gray-200 cert-panel-enter',
    mode === 'docked-left' && 'top-[69px] left-0 bottom-0 border-r border-gray-200 cert-panel-dock-left',
    mode === 'docked-right' && 'top-[69px] right-0 bottom-0 border-l border-gray-200 cert-panel-dock-right',
    mode === 'docked-bottom' && 'left-0 right-0 bottom-0 border-t border-gray-200 cert-panel-dock-bottom',
  )

  const containerStyle: React.CSSProperties = {
    borderRadius: mode === 'floating' ? 'var(--ui-radius, 12px)' : undefined,
    ...(mode === 'floating'
      ? {
          width: 540,
          height: '80vh',
          maxHeight: 740,
          top: dragPos ? dragPos.y : '50%',
          left: dragPos ? dragPos.x : '50%',
          transform: dragPos ? undefined : 'translate(-50%, -50%)',
        }
      : mode === 'docked-left'
        ? { width: 440 }
        : mode === 'docked-right'
          ? { width: 440 }
          : mode === 'docked-bottom'
            ? { height: 360 }
            : {}),
  }

  // Panel content (shared across floating / docked modes)
  const panelContent = loading ? (
    <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
      Loading certification progress...
    </div>
  ) : (
    <div className="flex-1 overflow-y-auto overscroll-contain p-5 space-y-6">
      {/* Hero Section */}
      {progress?.certified ? (
        <CertifiedBanner />
      ) : (
        <div
          className="flex items-center gap-5 p-4 bg-white border border-gray-200"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <div className="relative shrink-0">
            <ProgressRing
              percentage={overallPct}
              color={levelConfig.color}
              size={mode === 'docked-bottom' ? 80 : 100}
              strokeWidth={mode === 'docked-bottom' ? 6 : 8}
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold text-gray-900">{Math.round(overallPct)}%</span>
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: levelConfig.color }}>
                {levelConfig.label}
              </span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-bold text-gray-900 mb-0.5">Vandal Workflow Architect</h2>
            <p className="text-xs text-gray-500 mb-3">Complete all 11 modules to earn your certification</p>
            <XPBar current={displayXp} nextThreshold={nextLevel.xp} prevThreshold={prevLevel.xp} nextLevel={nextLevel.name} />
            <div className="flex flex-wrap gap-2 mt-3">
              <div className="flex items-center gap-1 px-2 py-1 bg-gray-50 border border-gray-200 text-xs" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
                <Award size={12} style={{ color: 'var(--highlight-color)' }} />
                <span className="font-semibold text-gray-900">{completedCount}</span>
                <span className="text-gray-500">/ 11</span>
              </div>
              <div className="flex items-center gap-1 px-2 py-1 bg-gray-50 border border-gray-200 text-xs" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
                <Zap size={12} style={{ color: 'var(--highlight-color)' }} />
                <span className="font-semibold text-gray-900">{displayXp}</span>
                <span className="text-gray-500">/ {TOTAL_XP}</span>
              </div>
              {(progress?.streak_days || 0) > 0 && (
                <div className="flex items-center gap-1 px-2 py-1 bg-orange-50 border border-orange-200 text-xs" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
                  <Flame size={12} className="text-orange-500" />
                  <span className="font-semibold text-orange-700">{progress?.streak_days}</span>
                  <span className="text-orange-600">streak</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Journey Map */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Training Modules</h3>
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
              lab_space_id: progress.modules[activeModuleDef.id].lab_space_id,
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
      <div className="p-4 bg-white border border-gray-200" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
        <h3 className="text-xs font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
          <Cog size={12} /> Level Progression
        </h3>
        <div className="flex items-center gap-0.5">
          {LEVEL_THRESHOLDS.map((lvl, i) => {
            const config = LEVEL_CONFIG[lvl.name]
            const reached = totalXp >= lvl.xp
            const isCurrent = level === lvl.name
            return (
              <div key={lvl.name} className="flex-1 flex flex-col items-center">
                <div
                  className={cn('w-full h-1.5 transition-all duration-500', i === 0 && 'rounded-l-full', i === LEVEL_THRESHOLDS.length - 1 && 'rounded-r-full')}
                  style={{ background: reached ? config.color : '#e5e7eb' }}
                />
                <div
                  className={cn('mt-1.5 text-[9px] font-medium text-center transition-all', isCurrent ? 'font-bold' : reached ? '' : 'text-gray-400')}
                  style={reached ? { color: config.color } : undefined}
                >
                  {config.label}
                </div>
                {isCurrent && <div className="w-1 h-1 rounded-full mt-0.5" style={{ background: config.color }} />}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )

  return createPortal(
    <>
      {/* Subtle backdrop for floating mode */}
      {mode === 'floating' && (
        <div
          className="fixed inset-0 z-[8999] bg-black/10 cert-fade-in"
          onClick={() => setMode('collapsed')}
        />
      )}

      <div data-cert-panel className={containerClass} style={containerStyle}>
        {/* Title bar */}
        <div
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 border-b border-gray-200 shrink-0 select-none',
            mode === 'floating' && 'cursor-grab active:cursor-grabbing',
          )}
          style={mode === 'floating' ? { borderRadius: 'var(--ui-radius, 12px) var(--ui-radius, 12px) 0 0' } : undefined}
          onPointerDown={handleDragStart}
          onPointerMove={handleDragMove}
          onPointerUp={handleDragEnd}
        >
          {mode === 'floating' && <GripHorizontal size={14} className="text-gray-300 shrink-0" />}
          <Award size={16} className="text-highlight shrink-0" style={{ color: 'var(--highlight-color)' }} />
          <span className="text-sm font-bold text-gray-900 flex-1">Certification</span>

          {/* Mode toggles */}
          <div className="flex items-center gap-0.5" onPointerDown={e => e.stopPropagation()}>
            {MODE_ICONS.map(({ mode: m, icon: Icon, label }) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                title={label}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  mode === m ? 'bg-gray-100 text-gray-900' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50',
                )}
              >
                <Icon size={14} />
              </button>
            ))}
          </div>

          <button onPointerDown={e => e.stopPropagation()} onClick={closePanel} title="Close" className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-50 ml-1">
            <X size={14} />
          </button>
        </div>

        {/* Panel body */}
        {panelContent}
      </div>

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
