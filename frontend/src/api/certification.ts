import { apiFetch, ApiError, rawFetch } from './client'
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
  return apiFetch<{ provisioned_docs: string[] }>(
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

/** Download the caller's certificate PDF. The server 404s until they are certified. */
export async function downloadCertificate(): Promise<void> {
  const res = await rawFetch('/api/certification/certificate', { method: 'GET' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Download failed' }))
    throw new ApiError(res.status, body.detail || 'Download failed')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'vandal-workflow-architect-certificate.pdf'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
