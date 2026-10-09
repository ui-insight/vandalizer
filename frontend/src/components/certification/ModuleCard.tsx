import { BookOpen, Check, Lock, Star } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { ModuleDefinition } from '../../types/certification'
import { ICON_MAP } from './constants'
import { hasOutcomeAssessment } from '../../lib/certificationAssessment'

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex gap-0.5" role="img" aria-label={`${count} of ${max} stars`}>
      {Array.from({ length: max }).map((_, i) => (
        <Star
          aria-hidden="true"
          key={i}
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

export function ModuleCard({ module, completed, stars, locked, active, onClick, previousModuleTitle, lockedReason }: {
  module: ModuleDefinition
  completed: boolean
  stars: number
  locked: boolean
  active: boolean
  onClick: () => void
  previousModuleTitle?: string
  lockedReason?: string
}) {
  const Icon = ICON_MAP[module.icon] || BookOpen

  return (
    <button
      onClick={onClick}
      disabled={locked}
      aria-current={active ? 'step' : undefined}
      className={cn(
        'relative flex flex-col items-start p-5 text-left border-2 transition-all duration-300',
        'hover:shadow-lg group w-full',
        locked && 'cursor-not-allowed hover:shadow-none bg-gray-50',
        completed && !active && 'border-green-200 bg-green-50/50',
        active && 'border-highlight bg-highlight/5 shadow-lg',
        !completed && !active && !locked && 'border-gray-200 bg-white hover:border-highlight',
      )}
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      {/* Module number badge */}
      <div
        className={cn(
          'absolute -top-3 -left-1 w-7 h-7 flex items-center justify-center text-xs font-bold',
          completed ? 'bg-green-700 text-white' : locked ? 'bg-gray-200 text-gray-700' : 'bg-highlight text-highlight-text',
        )}
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
      >
        {completed ? <Check size={14} aria-hidden="true" /> : module.number}
      </div>

      {/* Icon + Title */}
      <div className="flex items-center gap-2 mb-2 mt-1">
        <Icon
          aria-hidden="true"
          size={20}
          className={cn(
            completed ? 'text-green-700' : 'text-gray-600 group-hover:text-highlight',
            'transition-colors',
          )}
        />
        <span className="font-semibold text-sm text-gray-900">{module.title}</span>
      </div>

      <p className="text-xs text-gray-600 mb-3 line-clamp-2">
        {module.subtitle}
      </p>
      {locked && <p className="mb-3 flex items-start gap-2 text-xs text-gray-700"><Lock size={14} aria-hidden="true" className="shrink-0" /><span>Locked. {lockedReason || (previousModuleTitle ? `Complete ${previousModuleTitle} to unlock.` : 'Complete the required earlier modules to unlock.')}</span></p>}
      {completed && <p className="mb-2 text-xs font-semibold text-green-800">Completed</p>}

      {/* Bottom row: assessed credit and XP */}
      <div className="flex flex-wrap gap-2 items-center justify-between w-full mt-auto">
        {hasOutcomeAssessment(module) ? <span className="text-xs text-gray-700">Required outcomes</span> : <Stars count={stars} size={14} />}
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'text-xs font-bold px-2 py-0.5',
              completed ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600',
            )}
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            {module.xp} XP
          </span>
        </div>
      </div>
    </button>
  )
}
