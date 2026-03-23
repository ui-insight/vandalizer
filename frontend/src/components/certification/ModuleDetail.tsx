import { useState, useCallback } from 'react'
import {
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Lightbulb,
  Loader2,
  Star,
  Target,
  Upload,
  Zap,
} from 'lucide-react'
import { cn } from '../../lib/cn'
import { useToast } from '../../contexts/ToastContext'
import type { ModuleDefinition, CertExercise } from '../../types/certification'
import { ICON_MAP } from './constants'
import { SelfAssessment, MODULE_ASSESSMENTS } from './SelfAssessment'
import { LessonStepper } from './LessonStepper'

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
        />
      ))}
    </div>
  )
}

function ProgressWidget({ moduleProgress, lessonsCount }: {
  moduleProgress: { completed: boolean; stars: number; attempts: number } | null
  lessonsCount: number
}) {
  const completed = moduleProgress?.completed || false
  return (
    <div
      className="flex items-center gap-4 p-3 bg-gray-50 border border-gray-200 text-xs"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center gap-1.5">
        <BookOpen size={12} className="text-gray-400" />
        <span className="text-gray-600">Lessons: {lessonsCount}</span>
      </div>
      <div className="w-px h-4 bg-gray-200" />
      <div className="flex items-center gap-1.5">
        <Target size={12} className="text-gray-400" />
        <span className="text-gray-600">
          Challenge: {completed ? 'Complete' : 'Not started'}
        </span>
      </div>
      <div className="w-px h-4 bg-gray-200" />
      <Stars count={moduleProgress?.stars || 0} size={12} />
    </div>
  )
}

export function ModuleDetail({ module, moduleProgress, onValidate, onComplete, onProvision, onSubmitAssessment, onTabChange, exercise, validating, completing, provisioning, submittingAssessment }: {
  module: ModuleDefinition
  moduleProgress: { completed: boolean; stars: number; attempts: number; provisioned_docs?: string[]; self_assessment?: Record<string, string> } | null
  onValidate: () => void
  onComplete: () => void
  onProvision: () => void
  onSubmitAssessment: (answers: Record<string, string>) => void
  onTabChange?: () => void
  exercise: CertExercise | null
  validating: boolean
  completing: boolean
  provisioning: boolean
  submittingAssessment: boolean
}) {
  const [tab, setTab] = useState<'learn' | 'challenge'>('learn')

  const handleTabChange = (t: 'learn' | 'challenge') => {
    setTab(t)
    onTabChange?.()
  }
  const [showTips, setShowTips] = useState(false)
  const { toast } = useToast()
  const Icon = ICON_MAP[module.icon] || BookOpen
  const completed = moduleProgress?.completed || false
  const isProvisioned = (moduleProgress?.provisioned_docs?.length ?? 0) > 0
  const hasDocuments = (exercise?.documents?.length ?? 0) > 0

  const handleAllLessonsRead = useCallback(() => {
    toast('All lessons complete \u2014 ready for the challenge!', 'success')
  }, [toast])

  return (
    <div
      className="bg-white border-2 border-highlight/30 cert-slide-in overflow-hidden"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      {/* Header */}
      <div className="p-6 pb-0">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 flex items-center justify-center bg-highlight/10"
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <Icon size={22} className="text-highlight" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">
                Module {module.number}: {module.title}
              </h3>
              <p className="text-sm text-gray-500">{module.subtitle}</p>
            </div>
          </div>
          {completed && <Stars count={moduleProgress?.stars || 0} size={20} />}
        </div>

        {/* Progress widget */}
        <div className="mb-3">
          <ProgressWidget moduleProgress={moduleProgress} lessonsCount={module.lessons.length} />
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-200">
          <button
            onClick={() => handleTabChange('learn')}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px',
              tab === 'learn'
                ? 'border-highlight text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
            style={tab === 'learn' ? { borderColor: 'var(--highlight-color)' } : undefined}
          >
            <span className="flex items-center gap-1.5">
              <BookOpen size={14} />
              Learn
            </span>
          </button>
          <button
            onClick={() => handleTabChange('challenge')}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px',
              tab === 'challenge'
                ? 'border-highlight text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
            style={tab === 'challenge' ? { borderColor: 'var(--highlight-color)' } : undefined}
          >
            <span className="flex items-center gap-1.5">
              <Target size={14} />
              Challenge
            </span>
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="p-6">
        {tab === 'learn' ? (
          <div className="space-y-4">
            <p className="text-sm text-gray-700 mb-2">{module.description}</p>

            {/* LessonStepper replaces scrollable lesson list */}
            <LessonStepper
              lessons={module.lessons}
              moduleId={module.id}
              onAllLessonsRead={handleAllLessonsRead}
              onGoToChallenge={() => setTab('challenge')}
            />
          </div>
        ) : (
          <div>
            {/* Self-assessment (modules with reflection questions) */}
            {MODULE_ASSESSMENTS[module.id] && (
              <SelfAssessment
                moduleId={module.id}
                existingAnswers={moduleProgress?.self_assessment}
                onSubmit={onSubmitAssessment}
                submitting={submittingAssessment}
              />
            )}

            {/* Set Up Lab button */}
            {hasDocuments && (
              <div
                className={cn(
                  'mb-5 p-4 border-2',
                  isProvisioned ? 'border-green-200 bg-green-50/50' : 'border-blue-200 bg-blue-50/50',
                )}
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {isProvisioned ? (
                      <CheckCircle2 size={18} className="text-green-600" />
                    ) : (
                      <Upload size={18} className="text-blue-600" />
                    )}
                    <div>
                      <span className={cn('text-sm font-semibold', isProvisioned ? 'text-green-800' : 'text-blue-800')}>
                        {isProvisioned ? 'Documents ready in your workspace' : 'Add sample documents to your workspace'}
                      </span>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {exercise?.documents.map(d => d.replace('.pdf', '')).join(', ')}
                      </p>
                      {isProvisioned && (
                        <a
                          href="/"
                          className="text-xs font-medium mt-1 inline-block hover:underline"
                          style={{ color: 'var(--highlight-color)' }}
                        >
                          Open Workspace &rarr;
                        </a>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={onProvision}
                    disabled={provisioning || isProvisioned}
                    className={cn(
                      'flex items-center gap-2 px-4 py-2 text-sm font-semibold transition-all disabled:opacity-50',
                      isProvisioned
                        ? 'bg-green-100 text-green-700 cursor-default'
                        : 'bg-blue-600 text-white hover:bg-blue-700',
                    )}
                    style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                  >
                    {provisioning ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Setting up...
                      </>
                    ) : isProvisioned ? (
                      <>
                        <Check size={14} />
                        Ready
                      </>
                    ) : (
                      <>
                        <Upload size={14} />
                        Set Up Lab
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Step-by-step instructions */}
            {exercise?.instructions && exercise.instructions.length > 0 && (
              <div className="mb-5">
                <h4 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
                  <Target size={14} />
                  Exercise Steps
                </h4>
                <ol className="space-y-2">
                  {exercise.instructions.map((instruction, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <div
                        className={cn(
                          'w-5 h-5 flex items-center justify-center shrink-0 mt-0.5',
                          completed ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500',
                        )}
                        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                      >
                        {completed ? <Check size={12} /> : <span className="text-xs font-medium">{i + 1}</span>}
                      </div>
                      <span
                        className={cn('text-gray-700', completed && 'text-green-800')}
                        dangerouslySetInnerHTML={{
                          __html: instruction
                            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                            .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 bg-gray-100 rounded text-xs font-mono">$1</code>'),
                        }}
                      />
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* Expected fields callout */}
            {exercise?.expected_fields && exercise.expected_fields.length > 0 && (
              <div
                className="mb-5 p-3 bg-purple-50 border border-purple-200"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <h4 className="text-xs font-bold uppercase tracking-wider text-purple-600 mb-2">
                  Your SearchSet should include:
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {exercise.expected_fields.map((field) => (
                    <span
                      key={field}
                      className="inline-flex items-center px-2 py-1 bg-white border border-purple-200 text-xs font-medium text-purple-800"
                      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                    >
                      {field}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Star criteria */}
            {exercise?.star_criteria && (
              <div
                className="mb-5 p-3 bg-amber-50 border border-amber-200"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-700 mb-2 flex items-center gap-1">
                  <Star size={12} className="fill-amber-400 text-amber-400" />
                  Star Criteria
                </h4>
                <div className="space-y-1.5">
                  {Object.entries(exercise.star_criteria).map(([level, criteria]) => (
                    <div key={level} className="flex items-start gap-2 text-sm">
                      <Stars count={Number(level)} max={3} size={12} />
                      <span className="text-gray-700">{criteria}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tips */}
            <div className="mb-5">
              <button
                onClick={() => setShowTips(!showTips)}
                className="flex items-center gap-1.5 text-sm font-semibold text-gray-600 hover:text-gray-900"
              >
                <Lightbulb size={14} className="text-yellow-500" />
                Tips & Hints
                {showTips ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {showTips && (
                <ul className="mt-2 space-y-1.5 pl-5">
                  {module.tips.map((tip, i) => (
                    <li key={i} className="text-sm text-gray-600 list-disc">{tip}</li>
                  ))}
                </ul>
              )}
            </div>

            {/* Incomplete requirements warning */}
            {!completed && (() => {
              const assessmentDef = MODULE_ASSESSMENTS[module.id]
              const needsAssessment = assessmentDef &&
                !assessmentDef.questions.every(q => moduleProgress?.self_assessment?.[q.key])
              const needsLab = hasDocuments && !isProvisioned
              if (!needsAssessment && !needsLab) return null
              return (
                <div
                  className="mb-4 p-3 bg-amber-50 border border-amber-200 text-sm text-amber-800"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <p className="font-semibold mb-1">Before you can complete this module:</p>
                  <ul className="list-disc pl-4 space-y-0.5 text-amber-700">
                    {needsAssessment && <li>Complete the self-assessment above</li>}
                    {needsLab && <li>Set up your lab environment</li>}
                  </ul>
                </div>
              )
            })()}

            {/* Action buttons */}
            <div className="flex items-center gap-3">
              <button
                onClick={onValidate}
                disabled={validating}
                className="flex items-center gap-2 px-4 py-2.5 border-2 border-gray-200 text-sm font-semibold text-gray-700 hover:border-highlight hover:text-highlight-text hover:bg-highlight transition-all disabled:opacity-50"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <FlaskConical size={16} />
                {validating ? 'Checking...' : 'Check Progress'}
              </button>
              {!completed && (
                <button
                  onClick={onComplete}
                  disabled={completing}
                  className="flex items-center gap-2 px-4 py-2.5 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all disabled:opacity-50"
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <Zap size={16} />
                  {completing ? 'Completing...' : 'Complete Module'}
                </button>
              )}
            </div>

            {moduleProgress && (
              <p className="mt-3 text-xs text-gray-400">
                {moduleProgress.attempts} attempt{moduleProgress.attempts !== 1 ? 's' : ''}
                {completed && moduleProgress.completed ? ' \u00b7 Completed' : ''}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
