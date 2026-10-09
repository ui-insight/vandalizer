import type { CourseIdentity, ModuleDefinition, PendingCompletion } from '../types/certification'
import type { SupportDraftContext } from '../utils/supportPanel'

export function certificationSupportDraft(course: CourseIdentity, module: ModuleDefinition, attempt: PendingCompletion): SupportDraftContext {
  return {
    key: `certification:${course.enrollment_id}:${attempt.attempt_id}`,
    subject: `Certification completion needs review: ${module.title}`,
    message: [
      'My certification submission needs review before I can continue.',
      'Please check the saved assessment and preserve my existing credit.',
      '',
      `Course: ${course.course_title ?? course.course_version ?? 'Certification'}`,
      `Course version: ${course.course_version ?? 'Not available'}`,
      `Enrollment: ${course.enrollment_id ?? 'Not available'}`,
      `Module: ${module.title} (${module.id})`,
      `Assessment reference: ${attempt.attempt_id}`,
      `Status shown: ${attempt.state}`,
      '',
      'Additional details (optional):',
    ].join('\n'),
  }
}
