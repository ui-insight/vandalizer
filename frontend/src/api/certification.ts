import { apiFetch } from './client'
import type { CertificationProgress, ValidationResult, CompletionResult } from '../types/certification'

export function getProgress() {
  return apiFetch<CertificationProgress>('/api/certification/progress')
}

export function validateModule(moduleId: string) {
  return apiFetch<ValidationResult>(`/api/certification/modules/${moduleId}/validate`, { method: 'POST' })
}

export function completeModule(moduleId: string) {
  return apiFetch<CompletionResult>(`/api/certification/modules/${moduleId}/complete`, { method: 'POST' })
}
