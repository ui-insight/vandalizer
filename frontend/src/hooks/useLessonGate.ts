import { useCallback } from 'react'
import { answerLessonCheck, markLessonRead } from '../api/certification'
import { useCertificationPanelOptional } from '../contexts/CertificationPanelContext'
import type { LessonSection } from '../types/certification'

/**
 * Which of a module's lessons are read and which may be opened, from the
 * server's record, for the learning panel and the chat lesson card alike.
 *
 * Support ticket: opening a lesson counted as reading it, so Next lesson
 * through a module "read" all of it in seconds. A lesson with a knowledge
 * check is read only once its check is answered correctly, and where the
 * module's checks are required, a lesson opens only after every lesson
 * before it is read. Modules already under way and unlocked learners are
 * not gated (the server's lesson_checks_required).
 */
export function useLessonGate(moduleId: string, lessons: LessonSection[], enrollmentId?: string) {
  const certification = useCertificationPanelOptional()
  const progress = certification?.progress
  const required = progress?.lesson_checks_required?.[moduleId] === true
  const read = new Set(progress?.lessons_read?.[moduleId] ?? [])
  const firstUnread = lessons.findIndex(lesson => !lesson.id || !read.has(lesson.id))
  const noteLessonsRead = certification?.noteLessonsRead

  const isRead = (index: number) => { const id = lessons[index]?.id; return !!id && read.has(id) }
  const canOpen = (index: number) => !required || firstUnread === -1 || index <= firstUnread

  const opened = useCallback((lessonId: string) => {
    markLessonRead(moduleId, lessonId, enrollmentId)
      .then(result => noteLessonsRead?.(moduleId, result.lesson_ids_read ?? []))
      .catch(() => {})
  }, [moduleId, enrollmentId, noteLessonsRead])

  const answer = useCallback(async (lessonId: string, choice: number) => {
    const result = await answerLessonCheck(moduleId, lessonId, choice, enrollmentId)
    noteLessonsRead?.(moduleId, result.lesson_ids_read ?? [])
    return result
  }, [moduleId, enrollmentId, noteLessonsRead])

  return { required, isRead, canOpen, firstUnread, allRead: lessons.length > 0 && firstUnread === -1, opened, answer }
}
