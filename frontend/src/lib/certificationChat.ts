import type { CertificationProgress, CourseDefinition } from '../types/certification'
import { MODULES as LEGACY_MODULES } from '../components/certification/modules'

/**
 * Kickoff messages for the certification course in chat (certification tools
 * + cards): the home CTA and chat cards send these. The account menu, rail
 * badge and /certification URL open the learning panel instead until the
 * chat course is reliable for every module.
 */
export const START_CERTIFICATION_MESSAGE = 'Start the Vandalizer certification course — show me where to begin.'
export const CONTINUE_CERTIFICATION_MESSAGE = 'Continue my certification — show my progress and the next module.'
export const REVIEW_CERTIFICATION_MESSAGE = 'Show my completed certification and what each module covered.'

export interface CertificationChatEntry {
  label: string
  message: string
  certified: boolean
}

export function certificationChatEntry(
  progress: CertificationProgress | null | undefined,
  course: CourseDefinition | null | undefined,
): CertificationChatEntry {
  if (progress?.certified) {
    return { label: 'Review completed course', message: REVIEW_CERTIFICATION_MESSAGE, certified: true }
  }
  const moduleIds = progress?.module_ids ?? course?.modules.map(module => module.id)
  const selectedModules = moduleIds
    ? moduleIds.map(id => progress?.modules[id])
    : Object.values(progress?.modules ?? {})
  const completedCount = selectedModules.filter(module => module?.completed).length
  // Versioned metadata supplies membership and the denominator; the fallback
  // is the unversioned course's own module list, not a separate number.
  const total = progress?.modules_total ?? course?.modules.length ?? LEGACY_MODULES.length
  const hasSavedWork = completedCount > 0 || !!progress?.learning_position || !!progress?.pending_completions?.length
    || selectedModules.some(module => module?.scenario_attempt_id || module?.self_assessment || module?.provisioned_docs?.length)
  if (hasSavedWork) {
    return { label: `Continue certification (${completedCount}/${total})`, message: CONTINUE_CERTIFICATION_MESSAGE, certified: false }
  }
  return { label: 'Start the certification course', message: START_CERTIFICATION_MESSAGE, certified: false }
}
