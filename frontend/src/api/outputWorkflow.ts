import { apiFetch, rawFetch, ApiError } from './client'
import type { OutputList, OutputCapture, OutputRun, OutputInspection, OutputHandoff, OutputReview, OutputScope, OutputRequest, OutputSaved, OutputOrigin } from '../types/outputWorkflow'
const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const getOutputWork = (enrollmentId: string) => apiFetch<OutputList>(path('modules/output_delivery/output-workflows', enrollmentId))
export const getOutputCapture = (enrollmentId: string, id: string) => apiFetch<OutputCapture>(path(`output-captures/${encodeURIComponent(id)}`, enrollmentId))
export const getOutputRun = (enrollmentId: string, id: string) => apiFetch<OutputRun>(path(`output-runs/${encodeURIComponent(id)}`, enrollmentId))
export const getOutputInspection = (enrollmentId: string, id: string) => apiFetch<OutputInspection>(path(`output-file-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getOutputHandoff = (enrollmentId: string, id: string) => apiFetch<OutputHandoff>(path(`output-handoffs/${encodeURIComponent(id)}`, enrollmentId))
export const getOutputReview = (enrollmentId: string, id: string) => apiFetch<OutputReview>(path(`output-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getOutputScope = (enrollmentId: string, id: string) => apiFetch<OutputScope>(path(`output-scope-decisions/${encodeURIComponent(id)}`, enrollmentId))
export function saveOutputWork(enrollmentId: string, request: OutputRequest) {
  const routes = { capture: 'modules/output_delivery/output-captures', prepare: 'modules/output_delivery/output-runs',
    scope: 'output-runs/scope', execute: 'output-runs/execute', finalize: 'output-runs/finalize',
    inspection: 'modules/output_delivery/output-file-reviews', handoff: 'modules/output_delivery/output-handoffs', review: 'modules/output_delivery/output-reviews' }
  return apiFetch<OutputSaved>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
}
export async function getOutputFile(enrollmentId: string, origin: OutputOrigin, reference: string, kind: 'source' | 'file' | 'bundle', index: number, expectedSha256: string) {
  const response = await rawFetch(path(`output-files/${origin}/${encodeURIComponent(reference)}/${kind}`, enrollmentId) + `&file_index=${index}`)
  if (!response.ok) throw new ApiError(response.status, 'The original saved file could not be downloaded.')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength > 3 * 1024 * 1024) throw new Error('This download exceeds the saved file limit.')
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('')
  if (digest !== expectedSha256) throw new Error('The downloaded bytes do not match the selected saved file. Read the original run again.')
  return new Blob([bytes], { type: response.headers.get('content-type') || 'application/octet-stream' })
}
