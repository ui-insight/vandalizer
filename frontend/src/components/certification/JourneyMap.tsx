import { CheckCircle2, Clock, Sparkles } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { ModuleDefinition, CertificationProgress } from '../../types/certification'
import { TIERS } from './constants'
import { ModuleCard } from './ModuleCard'

export function JourneyMap({
  modules,
  progress,
  activeModule,
  isModuleLocked,
  onModuleClick,
}: {
  modules: ModuleDefinition[]
  progress: CertificationProgress | null
  activeModule: string | null
  isModuleLocked: (moduleId: string) => boolean
  onModuleClick: (moduleId: string) => void
}) {
  const totalMinutes = modules.reduce((sum, m) => sum + (m.estimatedMinutes || 0), 0)

  return (
    <div className="space-y-8">
      {/* Course-size line: time-strapped RAs decide whether to start here. */}
      <p className="text-xs text-gray-500 flex items-center gap-1.5 -mb-4">
        <Clock size={12} aria-hidden="true" />
        {modules.length} bite-sized modules, 10\u201325 minutes each \u2014 about {Math.round(totalMinutes / 60 * 2) / 2} hours in total.
        Do one whenever you have a gap; your place is always saved.
      </p>
      {TIERS.map((tier, tierIdx) => {
        const tierModules = tier.moduleIds
          .map(id => modules.find(m => m.id === id)!)
          .filter(Boolean)
        const completedInTier = tierModules.filter(
          m => progress?.modules[m.id]?.completed
        ).length
        const tierComplete = completedInTier === tierModules.length && tierModules.length > 0
        const pct = tierModules.length > 0 ? Math.round((completedInTier / tierModules.length) * 100) : 0

        return (
          <div key={tier.name}>
            {/* Tier header */}
            <div
              className={cn(
                'flex items-center gap-3 p-4 mb-3 border-2',
                tierComplete ? 'border-green-200 bg-green-50/50' : 'border-gray-200 bg-white',
              )}
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <div className={cn(
                'w-10 h-10 flex items-center justify-center shrink-0',
                tierComplete ? 'bg-green-100' : 'bg-gray-100',
              )} style={{ borderRadius: 'var(--ui-radius, 12px)' }}>
                {tierComplete ? (
                  <CheckCircle2 size={22} className="text-green-600" />
                ) : tierIdx === 0 ? (
                  <Sparkles size={22} className="text-blue-500" />
                ) : tierIdx === 1 ? (
                  <Sparkles size={22} className="text-purple-500" />
                ) : (
                  <Sparkles size={22} className="text-amber-500" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className={cn(
                    'text-sm font-bold',
                    tierComplete ? 'text-green-800' : 'text-gray-900',
                  )}>
                    {tier.name}
                  </h3>
                  <span className="text-xs text-gray-500">&middot;</span>
                  <span className="text-xs font-medium text-gray-500">{tier.theme}</span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5 italic">{tier.narrative}</p>
              </div>
              <div className="shrink-0 text-right">
                <span className={cn(
                  'text-sm font-bold',
                  tierComplete ? 'text-green-600' : pct > 0 ? 'text-highlight' : 'text-gray-500',
                )} style={pct > 0 && !tierComplete ? { color: 'var(--highlight-on-light, #806600)' } : undefined}>
                  {pct}%
                </span>
                <div className="text-[10px] text-gray-500">
                  {completedInTier}/{tierModules.length}
                </div>
              </div>
            </div>

            {/* Module cards with connecting line */}
            <div className="relative pl-6">
              {/* Vertical connecting line */}
              <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-gray-200" />

              <div className="space-y-3">
                {tierModules.map((module) => {
                  const modProgress = progress?.modules[module.id]
                  const locked = isModuleLocked(module.id)
                  const completed = modProgress?.completed || false
                  const prevModule = module.number > 0 ? modules.find(m => m.number === module.number - 1) : null

                  return (
                    <div key={module.id} className="relative flex items-start gap-3">
                      {/* Node dot on the line */}
                      <div
                        className={cn(
                          'absolute -left-6 top-5 w-3 h-3 rounded-full border-2 z-10',
                          completed ? 'bg-green-500 border-green-500' : locked ? 'bg-gray-200 border-gray-300' : 'bg-white border-highlight',
                        )}
                        style={!completed && !locked ? { borderColor: 'var(--highlight-on-light, #806600)' } : undefined}
                      />

                      <div className="flex-1">
                        <ModuleCard
                          module={module}
                          completed={completed}
                          stars={modProgress?.stars || 0}
                          locked={locked}
                          active={activeModule === module.id}
                          onClick={() => onModuleClick(module.id)}
                          previousModuleTitle={prevModule?.title}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
