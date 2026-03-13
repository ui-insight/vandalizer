import { BookOpen, Check, Clock, Lock, Star } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { ModuleDefinition } from '../../types/certification'
import { ICON_MAP } from './constants'

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

export function ModuleCard({ module, completed, stars, locked, active, onClick, previousModuleTitle }: {
  module: ModuleDefinition
  completed: boolean
  stars: number
  locked: boolean
  active: boolean
  onClick: () => void
  previousModuleTitle?: string
}) {
  const Icon = ICON_MAP[module.icon] || BookOpen

  return (
    <button
      onClick={onClick}
      disabled={locked}
      title={locked && previousModuleTitle ? `Complete "${previousModuleTitle}" to unlock` : undefined}
      className={cn(
        'relative flex flex-col items-start p-5 text-left border-2 transition-all duration-300',
        'hover:shadow-lg group w-full',
        locked && 'opacity-50 cursor-not-allowed hover:shadow-none',
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
          completed ? 'bg-green-500 text-white' : locked ? 'bg-gray-300 text-gray-500' : 'bg-highlight text-highlight-text',
        )}
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
      >
        {completed ? <Check size={14} /> : module.number}
      </div>

      {/* Lock overlay */}
      {locked && (
        <div className="absolute inset-0 flex items-center justify-center" style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
          <Lock size={24} className="text-gray-400" />
        </div>
      )}

      {/* Icon + Title */}
      <div className={cn('flex items-center gap-2 mb-2 mt-1', locked && 'invisible')}>
        <Icon
          size={20}
          className={cn(
            completed ? 'text-green-600' : 'text-gray-600 group-hover:text-highlight',
            'transition-colors',
          )}
        />
        <span className="font-semibold text-sm text-gray-900">{module.title}</span>
      </div>

      <p className={cn('text-xs text-gray-500 mb-3 line-clamp-2', locked && 'invisible')}>
        {module.subtitle}
      </p>

      {/* Bottom row: stars + XP + time */}
      <div className={cn('flex items-center justify-between w-full mt-auto', locked && 'invisible')}>
        <Stars count={stars} size={14} />
        <div className="flex items-center gap-2">
          {module.estimatedMinutes && (
            <span className="flex items-center gap-0.5 text-[10px] text-gray-400">
              <Clock size={10} />
              ~{module.estimatedMinutes}m
            </span>
          )}
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
