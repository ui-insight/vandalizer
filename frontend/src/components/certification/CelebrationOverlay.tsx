import { Award, Sparkles, Star, Zap } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { CompletionResult } from '../../types/certification'

const LEVEL_CONFIG: Record<string, { label: string; color: string }> = {
  novice:     { label: 'Novice',     color: '#9ca3af' },
  apprentice: { label: 'Apprentice', color: '#60a5fa' },
  builder:    { label: 'Builder',    color: '#34d399' },
  designer:   { label: 'Designer',   color: '#a78bfa' },
  engineer:   { label: 'Engineer',   color: '#f472b6' },
  specialist: { label: 'Specialist', color: '#fb923c' },
  expert:     { label: 'Expert',     color: '#f43f5e' },
  master:     { label: 'Master',     color: '#eab308' },
  architect:  { label: 'Architect',  color: '#eab308' },
}

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: max }).map((_, i) => (
        <Star
          key={i}
          size={size}
          className={cn(
            'transition-all duration-300',
            i < count ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300',
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
  const levelConfig = LEVEL_CONFIG[result.level] || LEVEL_CONFIG.novice

  return (
    <div className="fixed inset-0 z-[9998] flex items-center justify-center" onClick={onDismiss}>
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
        className="relative bg-white p-8 max-w-md w-full mx-4 text-center cert-pop-in"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        onClick={e => e.stopPropagation()}
      >
        {result.certified ? (
          <>
            <div className="cert-badge-glow mx-auto mb-4 w-24 h-24 flex items-center justify-center rounded-full"
              style={{ background: `linear-gradient(135deg, ${levelConfig.color}, var(--highlight-complement))` }}
            >
              <Award size={48} className="text-white" />
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-1">
              University of Idaho
            </p>
            <h2 className="text-2xl font-bold text-gray-900 mb-1 title-shimmer">
              Vandal Workflow Architect
            </h2>
            <p className="text-sm font-semibold mb-3" style={{ color: 'var(--highlight-color)' }}>
              Certified Professional
            </p>
            <p className="text-gray-600 text-sm mb-2">
              You have completed all 11 modules and demonstrated mastery of AI-powered document workflow design, construction, validation, and governance for research administration.
            </p>
            <p className="text-gray-500 text-xs">
              This credential recognizes your ability to turn real research administration processes into reliable, automated pipelines.
            </p>
          </>
        ) : tierCelebration ? (
          <>
            <div className="mb-4">
              <Award size={48} className="mx-auto text-highlight" style={{ color: 'var(--highlight-color)' }} />
            </div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-2">
              Tier Complete
            </p>
            <h2 className="text-xl font-bold text-gray-900 mb-3">{tierCelebration.tierName} Complete!</h2>
            <p className="text-sm text-gray-600 mb-2">{tierCelebration.message}</p>
          </>
        ) : (
          <>
            <div className="mb-4">
              <Sparkles size={48} className="mx-auto text-highlight" style={{ color: 'var(--highlight-color)' }} />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Module Complete!</h2>
          </>
        )}

        {/* XP earned */}
        <div className="flex items-center justify-center gap-6 my-6">
          <div className="text-center">
            <div className="text-3xl font-bold" style={{ color: 'var(--highlight-color)' }}>
              +{result.xp_earned}
            </div>
            <div className="text-xs text-gray-500 font-medium">XP EARNED</div>
          </div>
          <div className="w-px h-10 bg-gray-200" />
          <div className="text-center">
            <Stars count={result.stars} size={24} />
            <div className="text-xs text-gray-500 font-medium mt-1">STARS</div>
          </div>
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

        <button
          onClick={onDismiss}
          className="mt-2 px-6 py-2.5 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          {result.certified ? 'View Certificate' : 'Continue'}
        </button>
      </div>
    </div>
  )
}
