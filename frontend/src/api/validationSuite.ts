import { apiFetch, rawFetch, ApiError } from './client'
import type { ValidationList, ValidationCapture, ValidationRun, ValidationSuiteRecord, ValidationReview, ValidationScope, ValidationRequest, ValidationSaved, ValidationOrigin } from '../types/validationSuite'
const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const getValidationWork = (enrollmentId: string) => apiFetch<ValidationList>(path('modules/validation_qa/validation-suites', enrollmentId))
export const getValidationCapture = (enrollmentId: string, id: string) => apiFetch<ValidationCapture>(path(`validation-captures/${encodeURIComponent(id)}`, enrollmentId))
export const getValidationRun = (enrollmentId: string, id: string) => apiFetch<ValidationRun>(path(`validation-runs/${encodeURIComponent(id)}`, enrollmentId))
export const getValidationReview = (enrollmentId: string, id: string) => apiFetch<ValidationReview>(path(`validation-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getValidationSuite = (enrollmentId: string, id: string) => apiFetch<ValidationSuiteRecord>(path(`validation-suites/${encodeURIComponent(id)}`, enrollmentId))
export const getValidationScope = (enrollmentId: string, id: string) => apiFetch<ValidationScope>(path(`validation-scope-decisions/${encodeURIComponent(id)}`, enrollmentId))
export function saveValidationWork(enrollmentId: string, request: ValidationRequest) {
  const routes = { capture: 'modules/validation_qa/validation-captures', prepare: 'modules/validation_qa/validation-runs',
    scope: 'validation-runs/scope', execute: 'validation-runs/execute', finalize: 'validation-runs/finalize',
    suite: 'modules/validation_qa/validation-suites', review: 'modules/validation_qa/validation-reviews' }
  return apiFetch<ValidationSaved>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
}
export async function getValidationSource(enrollmentId: string, origin: ValidationOrigin, reference: string, sourceId: 'nsf' | 'nih', expectedSha256: string) {
  const response = await rawFetch(path(`validation-sources/${origin}/${encodeURIComponent(reference)}/${sourceId}`, enrollmentId))
  if (!response.ok) throw new ApiError(response.status, 'The original saved file could not be downloaded.')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength > 3 * 1024 * 1024) throw new Error('This download exceeds the saved file limit.')
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('')
  if (digest !== expectedSha256) throw new Error('The downloaded bytes do not match the selected saved file. Read the original run again.')
  return new Blob([bytes], { type: response.headers.get('content-type') || 'application/octet-stream' })
}
