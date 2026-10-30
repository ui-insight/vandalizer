import { useState } from 'react'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { MODULES } from '../certification/modules'
import { ChatLessonReader } from './ChatLessonReader'

/** Starting authored teaching uses the same course definition as the panel. */
export function ChatModuleLessons({ content }: { content: Record<string, unknown> }) {
  const certification = useCertificationPanelOptional()
  const [open, setOpen] = useState(false)
  const { progress, course } = certification ?? {}
  const enrolled = typeof content.enrollment_id === 'string'
  const matches = !!progress && (enrolled
    ? !!course && course.enrollment_id === content.enrollment_id && progress.enrollment_id === content.enrollment_id
      && course.course_version === content.course_version && course.manifest_sha256 === content.manifest_sha256
      && progress.manifest_sha256 === course.manifest_sha256
    : !progress.enrollment_id && !course)
  const module = matches ? (enrolled ? course?.modules : MODULES)?.find(item => item.id === content.module_id) : undefined
  const lesson = module?.lessons[0]
  if (!module || !lesson?.id) return certification ? <button type="button" className="chat-action-btn" onClick={certification.openPanel}>Open lessons in learning panel</button> : null
  return <div className="w-full min-w-0">
    <button type="button" className="chat-action-btn" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Close lessons' : `Start the lessons (${module.lessons.length})`}</button>
    {open && <div className="mt-4 border-t border-gray-300 pt-4"><ChatLessonReader key={`${content.enrollment_id ?? 'legacy'}:${content.manifest_sha256 ?? ''}:${module.id}`} content={{
      ...content, module_id: module.id, module_title: module.title, lesson_id: lesson.id, lesson_revision: lesson.revision,
      lesson_number: 1, lesson_count: module.lessons.length, is_last: module.lessons.length === 1,
      title: lesson.title, objective: lesson.objective, content: lesson.content, knowledge_check: lesson.knowledgeCheck, diagram: lesson.diagram,
    }} /></div>}
  </div>
}
