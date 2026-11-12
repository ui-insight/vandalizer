import type { KnowledgeCheckData } from '../types/certification'

export const practiceChanged = 'certification-practice-changed'
export type PracticeAttempt = { choice: number; savedAt: string }
export type PracticeScope = { userId: string; enrollmentId?: string; moduleId: string; lessonId: string; revision: number }

/** Browser-local formative history. Never sent to an assessment or progress API. */
export function practiceStorageKey(scope?: PracticeScope): string | undefined {
  if (!scope?.userId || !scope.moduleId || !scope.lessonId || !Number.isSafeInteger(scope.revision) || scope.revision < 1) return undefined
  return `cert-practice:${JSON.stringify([scope.userId, scope.enrollmentId ?? 'legacy', scope.moduleId, scope.lessonId, scope.revision])}`
}

export function readPractice(key: string, data: KnowledgeCheckData): PracticeAttempt[] {
  const raw = localStorage.getItem(key)
  if (!raw) return []
  try {
    const value = JSON.parse(raw)
    if (value.schema !== 1 || value.question !== JSON.stringify(data) || !Array.isArray(value.attempts)
      || value.attempts.length > 20 || !value.attempts.every((attempt: PracticeAttempt) => attempt
        && Number.isSafeInteger(attempt.choice) && attempt.choice >= 0 && attempt.choice < data.options.length
        && typeof attempt.savedAt === 'string' && Number.isFinite(Date.parse(attempt.savedAt)))) return []
    return value.attempts.map((attempt: PracticeAttempt) => ({ choice: attempt.choice, savedAt: attempt.savedAt }))
  } catch { return [] }
}

export function savePractice(key: string, data: KnowledgeCheckData, choice: number): PracticeAttempt[] {
  const attempts = [...readPractice(key, data), { choice, savedAt: new Date().toISOString() }].slice(-20)
  localStorage.setItem(key, JSON.stringify({ schema: 1, question: JSON.stringify(data), attempts }))
  window.dispatchEvent(new CustomEvent(practiceChanged, { detail: key }))
  return attempts
}
