import { apiFetch } from './client'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise } from '../types/certification'

export function getProgress() {
  return apiFetch<CertificationProgress>('/api/certification/progress')
}

export function validateModule(moduleId: string) {
  return apiFetch<ValidationResult>(`/api/certification/modules/${moduleId}/validate`, { method: 'POST' })
}

export function completeModule(moduleId: string) {
  return apiFetch<CompletionResult>(`/api/certification/modules/${moduleId}/complete`, { method: 'POST' })
}

export function provisionModule(moduleId: string) {
  return apiFetch<{ provisioned_docs: string[]; space_id: string | null }>(
    `/api/certification/modules/${moduleId}/provision`,
    { method: 'POST' },
  )
}

export function getExercise(moduleId: string) {
  return apiFetch<CertExercise>(`/api/certification/modules/${moduleId}/exercise`)
}

export function submitAssessment(moduleId: string, answers: Record<string, string>) {
  return apiFetch<{ stored: boolean }>(
    `/api/certification/modules/${moduleId}/assessment`,
    { method: 'POST', body: JSON.stringify({ answers }) },
  )
}
