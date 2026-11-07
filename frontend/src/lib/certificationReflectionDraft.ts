import type { AssessmentDefinition } from '../types/certification'

export function reflectionDraftKey(userId: string | undefined, moduleId: string, enrollmentId?: string) {
  return userId ? `cert-reflection-draft:${JSON.stringify([userId, enrollmentId ?? 'legacy', moduleId])}` : undefined
}

export function readReflectionDraft(key: string | undefined, definition: AssessmentDefinition): Record<string, string> {
  if (!key) return {}
  const raw = sessionStorage.getItem(key)
  if (!raw) return {}
  try {
    const value = JSON.parse(raw)
    if (value.schema !== 1 || value.definition !== JSON.stringify(definition) || !value.answers || typeof value.answers !== 'object' || Array.isArray(value.answers)) return {}
    return Object.fromEntries(definition.questions.flatMap(question => question.options.includes(value.answers[question.key]) ? [[question.key, value.answers[question.key]]] : []))
  } catch { return {} }
}

export function saveReflectionDraft(key: string, definition: AssessmentDefinition, answers: Record<string, string>) {
  sessionStorage.setItem(key, JSON.stringify({ schema: 1, definition: JSON.stringify(definition), answers }))
}
