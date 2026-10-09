import { FocusTrap } from '../shared/PanelFocusTrap'
import { Award, Sparkles, Star, Zap } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { CompletionResult } from '../../types/certification'
import { LEVEL_CONFIG } from './constants'

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex gap-0.5" role="img" aria-label={`${count} of ${max} stars`}>
      {Array.from({ length: max }).map((_, i) => (
        <Star
          key={i}
          aria-hidden="true"
          size={size}
          className={cn(
            'transition-all duration-300',
            i < count ? 'text-amber-700 fill-amber-700' : 'text-gray-500',
          )}
          style={i < count ? { animationDelay: `${i * 0.15}s` } : undefined}
        />
      ))}
    </div>
  )
}

export function CelebrationOverlay({
  result,
  onDismiss,
  tierCelebration,
}: {
  result: CompletionResult
  onDismiss: () => void
  tierCelebration?: { tierName: string; message: string } | null
}) {
  const levelConfig = LEVEL_CONFIG[result.level] || { ...LEVEL_CONFIG.novice, label: result.level.replaceAll('_', ' ') }
  const outcomeCompletion = result.validation.assessment_kind === 'selected_outcome_validation'

  return (
    <FocusTrap focusTrapOptions={{ escapeDeactivates: false, delayInitialFocus: false }}>
    <div data-cert-celebration role="dialog" aria-modal="true" aria-label={result.certified ? 'Course complete' : 'Module complete'} className="fixed inset-0 z-[9998] flex items-center justify-center" onClick={onDismiss} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onDismiss() } }}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 cert-fade-in" />

      {/* Confetti particles */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {Array.from({ length: 50 }).map((_, i) => (
          <div
            key={i}
            className="cert-confetti-piece"
            style={{
              '--x': `${Math.random() * 100}vw`,
              '--delay': `${Math.random() * 2}s`,
              '--color': ['#eab308', '#ef4444', '#3b82f6', '#10b981', '#8b5cf6', '#f97316'][i % 6],
              '--size': `${6 + Math.random() * 8}px`,
              '--drift': `${-30 + Math.random() * 60}px`,
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* Content */}
      <div
        className="relative flex max-h-[90dvh] w-full max-w-md flex-col overflow-hidden bg-white text-center cert-pop-in mx-4"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        onClick={e => e.stopPropagation()}
      >
        <div role="region" aria-label="Completion details" tabIndex={0} className="min-h-0 overflow-y-auto p-5 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-purple-700 sm:p-8">
        {result.certified ? (
          <>
            <div className="cert-badge-glow mx-auto mb-4 w-24 h-24 flex items-center justify-center rounded-full"
              style={{ background: `linear-gradient(135deg, ${levelConfig.color}, var(--highlight-complement))` }}
            >
              <Award size={48} className="text-white" />
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-1">
              University of Idaho
            </p>
            <h2 className="break-words text-2xl font-bold text-gray-900 mb-1 title-shimmer">
              {result.course_title || 'Vandal Workflow Architect'}
            </h2>
            <p className="text-sm font-semibold mb-3" style={{ color: 'var(--highlight-on-light, #806600)' }}>
              Certified Professional
            </p>
            {result.course_version && <p className="text-xs text-gray-600 mb-2">Course version: {result.course_version}</p>}
            <p className="text-gray-600 text-sm mb-2">
              {result.modules_total ? `You have completed all ${result.modules_total} modules in this course.` : 'You have completed the requirements for this course.'}
            </p>
            <p className="text-gray-500 text-xs">
              Your earned credential stays associated with the course you completed. Later course updates do not change it.
            </p>
          </>
        ) : tierCelebration ? (
          <>
            <div className="mb-4">
              <Award size={48} className="mx-auto text-highlight" style={{ color: 'var(--highlight-on-light, #806600)' }} />
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2">
              Tier Complete
            </p>
            <h2 className="text-xl font-bold text-gray-900 mb-3">{tierCelebration.tierName} Complete!</h2>
            <p className="text-sm text-gray-600 mb-2">{tierCelebration.message}</p>
          </>
        ) : (
          <>
            <div className="mb-4">
              <Sparkles size={48} className="mx-auto text-highlight" style={{ color: 'var(--highlight-on-light, #806600)' }} />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Module Complete!</h2>
          </>
        )}

        {/* XP earned */}
        <div className="flex items-center justify-center gap-6 my-6">
          <div className="text-center">
            <div className="text-3xl font-bold" style={{ color: 'var(--highlight-on-light, #806600)' }}>
              {result.credit_origin === 'transferred' ? result.xp_carried : `+${result.xp_earned}`}
            </div>
            <div className="text-xs text-gray-500 font-medium">{result.credit_origin === 'transferred' ? 'XP CARRIED · NO NEW REWARD' : 'XP EARNED'}</div>
          </div>
          {!outcomeCompletion && <><div className="w-px h-10 bg-gray-200" />
          <div className="text-center">
            <Stars count={result.stars} size={24} />
            <div className="text-xs text-gray-500 font-medium mt-1">STARS</div>
          </div></>}
        </div>

        {/* Level up */}
        {result.level_up && (
          <div
            className="flex items-center justify-center gap-2 py-2 px-4 mx-auto w-fit mb-4 cert-level-glow"
            style={{
              background: `${levelConfig.color}15`,
              border: `2px solid ${levelConfig.color}`,
              borderRadius: 'var(--ui-radius, 12px)',
            }}
          >
            <Zap size={16} style={{ color: levelConfig.color }} />
            <span className="text-sm font-bold" style={{ color: levelConfig.color }}>
              Level Up! You're now {levelConfig.label}
            </span>
          </div>
        )}

        </div>
        <div className="shrink-0 border-t border-gray-200 px-5 py-3 sm:px-8">
        <button
          onClick={onDismiss}
          className="min-h-11 max-w-full break-words px-4 py-2.5 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          {result.certified ? 'View Certificate' : 'Continue'}
        </button>
        </div>
      </div>
    </div>
    </FocusTrap>
  )
}
