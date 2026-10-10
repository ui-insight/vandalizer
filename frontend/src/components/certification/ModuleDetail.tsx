import { useState, useCallback, useEffect, useRef } from 'react'
import { hasOutcomeAssessment } from '../../lib/certificationAssessment'
import { ModuleOutcomePreview } from './ModuleOutcomePreview'
import type { ReadinessIdentity } from '../../api/moduleReadiness'
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Lightbulb,
  Star,
  Target,
  Zap,
} from 'lucide-react'
import { cn } from '../../lib/cn'
import { renderCertificationMarkdown } from '../../lib/certificationMarkdown'
import { useToast } from '../../contexts/ToastContext'
import type { ModuleDefinition, CertExercise, OutcomeCompletionSelection } from '../../types/certification'
import { ICON_MAP } from './constants'
import { SelfAssessment, MODULE_ASSESSMENTS } from './SelfAssessment'
import { LessonStepper } from './LessonStepper'
import { EditorialCorrection } from './EditorialCorrection'
import { ScenarioAssessment } from './ScenarioAssessment'
import { PracticalReview } from './PracticalReview'
import { ProcessDesign } from './ProcessDesign'
import { WorkflowDesign } from './WorkflowDesign'
import { ConnectedWorkflow } from './ConnectedWorkflow'
import { BudgetWorkflow } from './BudgetWorkflow'
import { OutputWorkflow } from './OutputWorkflow'
import { BatchAssessment } from './BatchAssessment'
import { GovernanceAssessment } from './GovernanceAssessment'
import { ValidationSuite } from './ValidationSuite'
import { LabSetupStatus } from './LabSetupStatus'

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex shrink-0 gap-0.5" role="img" aria-label={`${count} of ${max} stars`}>
      {Array.from({ length: max }).map((_, i) => (
        <Star
          aria-hidden="true"
          key={i}
          size={size}
          className={cn(
            'transition-all duration-300',
            i < count ? 'text-amber-700 fill-amber-700' : 'text-gray-500',
          )}
        />
      ))}
    </div>
  )
}

function ProgressWidget({ moduleProgress, lessonsCount, outcomeAssessment }: {
  moduleProgress: { completed: boolean; stars: number; attempts: number } | null
  lessonsCount: number
  outcomeAssessment: boolean
}) {
  const completed = moduleProgress?.completed || false
  return (
    <div
      className="flex flex-wrap items-center gap-2 sm:gap-4 p-3 bg-gray-50 border border-gray-200 text-xs"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center gap-1.5">
        <BookOpen size={12} aria-hidden="true" className="text-gray-400" />
        <span className="text-gray-600">Lessons: {lessonsCount}</span>
      </div>
      <div className="hidden sm:block w-px h-4 bg-gray-200" />
      <div className="flex items-center gap-1.5">
        <Target size={12} aria-hidden="true" className="text-gray-400" />
        <span className="text-gray-600">
          {outcomeAssessment ? `Module: ${completed ? 'Complete' : 'Not complete'}` : `Challenge: ${completed ? 'Complete' : 'Not started'}`}
        </span>
      </div>
      {!outcomeAssessment && <><div className="hidden sm:block w-px h-4 bg-gray-200" />
        <Stars count={moduleProgress?.stars || 0} size={12} /></>}
    </div>
  )
}

export function ModuleDetail({ module, moduleProgress, onValidate, onComplete, onProvision, onOpenWorkspace, onSubmitAssessment, onTabChange, exercise, validating, completing, provisioning, submittingAssessment, enrollmentId, savedLessonId, onSavePosition, onReloadPosition, onScenarioSaved, openChallengeRequest, courseIdentity, onCompleteOutcomes, outcomeCompletionPending, progressRefreshPending }: {
  module: ModuleDefinition
  moduleProgress: { completed: boolean; stars: number; attempts: number; provisioned_docs?: string[]; self_assessment?: Record<string, string>; scenario_attempt_id?: string } | null
  onValidate: () => void
  onComplete: () => void
  onProvision: () => void
  onOpenWorkspace?: () => Promise<void>
  onSubmitAssessment: (answers: Record<string, string>) => void
  onTabChange?: () => void
  exercise: CertExercise | null
  validating: boolean
  completing: boolean
  provisioning: boolean
  submittingAssessment: boolean
  enrollmentId?: string
  savedLessonId?: string
  onSavePosition?: (lessonId: string) => Promise<void>
  onReloadPosition?: () => Promise<void>
  onScenarioSaved?: () => Promise<void>
  openChallengeRequest?: number
  onCompleteOutcomes?: (selection: OutcomeCompletionSelection) => Promise<void>
  outcomeCompletionPending?: boolean
  progressRefreshPending?: boolean
  courseIdentity?: ReadinessIdentity
}) {
  const [tab, setTab] = useState<'learn' | 'challenge'>(() => openChallengeRequest === undefined ? 'learn' : 'challenge')
  const challengeButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (openChallengeRequest === undefined) return
    setTab('challenge')
    const frame = requestAnimationFrame(() => challengeButton.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [openChallengeRequest])

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
  const challengeNeedsLab = hasDocuments && !isProvisioned && !hasOutcomeAssessment(module)
  const assessmentDef = module.scenarioAssessment || module.processAssessment || module.workflowDesignAssessment || module.connectedWorkflowAssessment || module.budgetWorkflowAssessment || module.outputWorkflowAssessment || module.validationAssessment || module.batchAssessment || module.governanceAssessment ? null : module.assessment === undefined ? MODULE_ASSESSMENTS[module.id] : module.assessment

  const handleAllLessonsRead = useCallback(() => {
    if (!completed) {
      toast('All lessons viewed \u2014 ready for the challenge!', 'success')
    }
  }, [toast, completed])

  return (
    <div
      className="mx-auto w-full max-w-4xl bg-white border-2 border-highlight/30 cert-slide-in overflow-hidden"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      {/* Header */}
      <div className="p-[8px] pb-0 sm:p-6 sm:pb-0">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 flex items-center justify-center bg-highlight/10"
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <Icon size={22} className="text-highlight-on-light" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">
                Module {module.number}: {module.title}
              </h3>
              <p className="text-sm text-gray-500">
                {module.subtitle}
                <span className="text-gray-500"> · {enrollmentId ? 'Use Save this place to resume later.' : 'Reading place is saved in this browser.'}</span>
              </p>
            </div>
          </div>
          {completed && !hasOutcomeAssessment(module) && <Stars count={moduleProgress?.stars || 0} size={20} />}
        </div>

        {/* Progress widget */}
        <div className="mb-3">
          <ProgressWidget moduleProgress={moduleProgress} lessonsCount={module.lessons.length} outcomeAssessment={hasOutcomeAssessment(module)} />
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
            ref={challengeButton}
            onClick={() => handleTabChange('challenge')}
            disabled={challengeNeedsLab}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px',
              tab === 'challenge'
                ? 'border-highlight text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700',
              challengeNeedsLab && 'opacity-40 cursor-not-allowed',
            )}
            style={tab === 'challenge' ? { borderColor: 'var(--highlight-color)' } : undefined}
            title={challengeNeedsLab ? 'Set up your lab first to unlock the challenge' : undefined}
          >
            <span className="flex items-center gap-1.5">
              <Target size={14} />
              Challenge
            </span>
          </button>
        </div>
      </div>

      {/* Set Up Lab — shown above tab content so it's always accessible */}
      {hasDocuments && <div className="px-4 pt-4 sm:px-6">
        <LabSetupStatus key={`${enrollmentId || 'legacy'}:${module.id}`} assignmentKey={JSON.stringify(moduleProgress?.provisioned_docs || [])}
          moduleId={module.id} enrollmentId={enrollmentId} filenames={exercise!.documents}
          onProvision={onProvision} provisioning={provisioning} onOpenWorkspace={onOpenWorkspace} />
      </div>}

      {/* Tab content */}
      <div className="p-[8px] sm:p-6">
        {tab === 'challenge' && <EditorialCorrection moduleId={module.id} manifestSha256={courseIdentity?.manifest_sha256} content={module.description} />}
        {tab === 'learn' ? (
          <div className="mx-auto max-w-3xl space-y-4">
            <EditorialCorrection moduleId={module.id} manifestSha256={courseIdentity?.manifest_sha256} content={module.description} />
            <p className="text-sm text-gray-700 mb-2">{module.description}</p>

            {/* Assignment makes directions available; it does not prove readiness. */}
            {isProvisioned && exercise && (
              <div
                className="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-gray-50 border border-gray-200"
                style={{ borderRadius: 'var(--ui-radius, 12px)' }}
              >
                <span className="flex items-center gap-1.5 text-sm font-medium text-gray-700">
                  <BookOpen size={14} aria-hidden="true" className="shrink-0" />
                  {exercise.instructions.length} challenge steps
                </span>
                <button
                  onClick={() => handleTabChange('challenge')}
                  className="flex min-h-11 items-center gap-1 text-xs font-semibold hover:underline shrink-0"
                  style={{ color: 'var(--highlight-on-light, #806600)' }}
                >
                  Go to challenge
                  <ChevronRight size={12} />
                </button>
              </div>
            )}

            {/* LessonStepper replaces scrollable lesson list */}
            <LessonStepper
              lessons={module.lessons}
              moduleId={module.id}
              enrollmentId={enrollmentId}
              savedLessonId={savedLessonId}
              manifestSha256={courseIdentity?.manifest_sha256}
              onSavePosition={onSavePosition}
              onReloadPosition={onReloadPosition}
              exercise={exercise}
              onAllLessonsRead={handleAllLessonsRead}
              onGoToChallenge={() => challengeNeedsLab ? undefined : setTab('challenge')}
              onStepChange={onTabChange}
              isProvisioned={isProvisioned}
              hasDocuments={hasDocuments}
            />
          </div>
        ) : (
          <div>
            {module.governanceAssessment ? (enrollmentId ? <div className="space-y-6">
              {module.scenarioAssessment && <ScenarioAssessment key={`${enrollmentId}:${module.scenarioAssessment.bank_sha256}`} definition={module.scenarioAssessment} enrollmentId={enrollmentId} attemptId={moduleProgress?.scenario_attempt_id} onSaved={onScenarioSaved} />}
              <GovernanceAssessment key={`governance:${enrollmentId}:${module.governanceAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.governanceAssessment} />
            </div> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.batchAssessment ? (enrollmentId ? <BatchAssessment key={`batch:${enrollmentId}:${module.batchAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.batchAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.validationAssessment ? (enrollmentId ? <div className="space-y-6">
              {module.scenarioAssessment && <ScenarioAssessment key={`${enrollmentId}:${module.scenarioAssessment.bank_sha256}`} definition={module.scenarioAssessment} enrollmentId={enrollmentId} attemptId={moduleProgress?.scenario_attempt_id} onSaved={onScenarioSaved} />}
              <ValidationSuite key={`validation:${enrollmentId}:${module.validationAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.validationAssessment} />
            </div> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.outputWorkflowAssessment ? (enrollmentId ? <OutputWorkflow key={`output:${enrollmentId}:${module.outputWorkflowAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.outputWorkflowAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.budgetWorkflowAssessment ? (enrollmentId ? <BudgetWorkflow key={`budget:${enrollmentId}:${module.budgetWorkflowAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.budgetWorkflowAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.connectedWorkflowAssessment ? (enrollmentId ? <ConnectedWorkflow key={`connected:${enrollmentId}:${module.connectedWorkflowAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.connectedWorkflowAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.workflowDesignAssessment ? (enrollmentId ? <WorkflowDesign key={`workflow:${enrollmentId}:${module.workflowDesignAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.workflowDesignAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.processAssessment ? (enrollmentId ? <ProcessDesign key={`process:${enrollmentId}:${module.processAssessment.case_sha256}`} enrollmentId={enrollmentId} definition={module.processAssessment} /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.decisionPrompts?.length ? (enrollmentId ? <PracticalReview
              key={`${enrollmentId}:${module.id}`}
              enrollmentId={enrollmentId}
              moduleId={module.id}
              prompts={module.decisionPrompts}
              prepareEnabled={module.practicalPreparation === true}
              repairAssignment={module.repairAssignment}
              assignment={exercise}
            /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : module.scenarioAssessment ? (enrollmentId ? <ScenarioAssessment
              key={`${enrollmentId}:${module.scenarioAssessment.bank_sha256}`}
              definition={module.scenarioAssessment}
              enrollmentId={enrollmentId}
              attemptId={moduleProgress?.scenario_attempt_id}
              onSaved={onScenarioSaved}
            /> : <p role="alert">Refresh your course to load this assessment’s enrollment.</p>) : <>
            {/* Challenge overview */}
            {exercise?.overview && (
              <div className="cert-lesson-markdown text-sm text-gray-600 mb-5 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: renderCertificationMarkdown(exercise.overview) }}
              />
            )}

            {/* Self-assessment (modules with reflection questions) */}
            {assessmentDef && (
              <SelfAssessment
                moduleId={module.id}
                enrollmentId={enrollmentId}
                definition={assessmentDef}
                existingAnswers={moduleProgress?.self_assessment}
                onSubmit={onSubmitAssessment}
                submitting={submittingAssessment}
              />
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
                        className="w-5 h-5 flex items-center justify-center shrink-0 mt-0.5 bg-gray-100 text-gray-500"
                        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                      >
                        <span className="text-xs font-medium">{i + 1}</span>
                      </div>
                      <div
                        className="cert-lesson-markdown min-w-0 break-words text-gray-700"
                        dangerouslySetInnerHTML={{ __html: renderCertificationMarkdown(instruction) }}
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
                  Your Extraction should include:
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
                aria-expanded={showTips}
                aria-controls={`certification-tips-${module.id}`}
                className="flex items-center gap-1.5 text-sm font-semibold text-gray-600 hover:text-gray-900"
              >
                <Lightbulb size={14} className="text-yellow-500" />
                Tips & Hints
                {showTips ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {showTips && (
                <ul id={`certification-tips-${module.id}`} className="mt-2 space-y-1.5 pl-5">
                  {module.tips.map((tip, i) => (
                    <li key={i} className="text-sm text-gray-600 list-disc">{tip}</li>
                  ))}
                </ul>
              )}
            </div>

            {/* Incomplete requirements warning */}
            {!completed && (() => {
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
              <p className="mt-3 text-xs text-gray-500">
                {moduleProgress.attempts ?? 0} attempt{moduleProgress.attempts !== 1 ? 's' : ''}
                {completed && moduleProgress.completed ? ' \u00b7 Completed' : ''}
              </p>
            )}
            </>}
            {courseIdentity?.enrollment_id === enrollmentId && hasOutcomeAssessment(module) && courseIdentity &&
              <ModuleOutcomePreview identity={courseIdentity} moduleId={module.id} onComplete={onCompleteOutcomes} completed={completed} completionPending={outcomeCompletionPending} progressRefreshPending={progressRefreshPending} />}
          </div>
        )}
      </div>
    </div>
  )
}
