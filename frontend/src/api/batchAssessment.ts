import { apiFetch, rawFetch, ApiError } from './client'
import type { BatchList, BatchCapture, BatchRun, BatchReview, BatchScope, BatchRequest, BatchSaved, BatchOrigin } from '../types/batchAssessment'
const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const getBatchWork = (enrollmentId: string) => apiFetch<BatchList>(path('modules/batch_processing/batch-work', enrollmentId))
export const getBatchCapture = (enrollmentId: string, id: string) => apiFetch<BatchCapture>(path(`batch-captures/${encodeURIComponent(id)}`, enrollmentId))
export const getBatchRun = (enrollmentId: string, id: string) => apiFetch<BatchRun>(path(`batch-runs/${encodeURIComponent(id)}`, enrollmentId))
export const getBatchReview = (enrollmentId: string, id: string) => apiFetch<BatchReview>(path(`batch-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getBatchScope = (enrollmentId: string, id: string) => apiFetch<BatchScope>(path(`batch-scope-decisions/${encodeURIComponent(id)}`, enrollmentId))
export function saveBatchWork(enrollmentId: string, request: BatchRequest) {
  const routes = { capture: 'modules/batch_processing/batch-captures', prepare: 'modules/batch_processing/batch-runs',
    scope: 'batch-runs/scope', execute: 'batch-runs/execute', finalize: 'batch-runs/finalize',
    review: 'modules/batch_processing/batch-reviews' }
  return apiFetch<BatchSaved>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
}
export async function getBatchSource(enrollmentId: string, origin: BatchOrigin, reference: string, sourceId: 'proposal_1' | 'proposal_2' | 'proposal_3', expectedSha256: string) {
  const response = await rawFetch(path(`batch-sources/${origin}/${encodeURIComponent(reference)}/${sourceId}`, enrollmentId))
  if (!response.ok) throw new ApiError(response.status, 'The original saved file could not be downloaded.')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength > 3 * 1024 * 1024) throw new Error('This download exceeds the saved file limit.')
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('')
  if (digest !== expectedSha256) throw new Error('The downloaded bytes do not match the selected saved file. Read the original run again.')
  return new Blob([bytes], { type: response.headers.get('content-type') || 'application/octet-stream' })
}
