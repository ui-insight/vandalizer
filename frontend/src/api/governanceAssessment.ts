import { apiFetch, rawFetch, ApiError } from './client'
import type { GovernanceKind, GovernanceList, GovernanceRequest, GovernanceView, GovernanceAction } from '../types/governanceAssessment'
const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const governanceActionKind = (action: GovernanceAction): GovernanceKind => ['prepare', 'execute', 'finalize'].includes(action) ? 'run' : action as GovernanceKind
export const getGovernanceWork = (enrollmentId: string) => apiFetch<GovernanceList>(path('modules/governance/governance-work', enrollmentId))
export async function getGovernanceRecord(enrollmentId: string, kind: GovernanceKind, reference: string): Promise<GovernanceView> {
  const value = await apiFetch<GovernanceView['value']>(path(`governance/${kind}/${encodeURIComponent(reference)}`, enrollmentId))
  return { kind, value } as GovernanceView
}
export async function saveGovernanceWork(enrollmentId: string, request: GovernanceRequest): Promise<GovernanceView> {
  const routes: Record<GovernanceAction, string> = { capture: 'modules/governance/governance-captures', prepare: 'modules/governance/governance-runs',
    scope: 'governance-runs/scope', execute: 'governance-runs/execute', finalize: 'governance-runs/finalize', correction: 'governance/corrections',
    finding: 'governance/findings', memo: 'governance/memos', release: 'governance/releases', handoff: 'governance/handoffs', review: 'modules/governance/governance-reviews' }
  const value = await apiFetch<GovernanceView['value']>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
  return { kind: governanceActionKind(request.action), value } as GovernanceView
}
export type GovernanceDownload = { origin: Exclude<GovernanceKind, 'scope'>; reference: string; sourceId: 'award' | 'amendment' }
  | { origin: 'memo' | 'release' | 'handoff' | 'review'; reference: string; sourceId?: undefined }
export async function downloadGovernanceFile(enrollmentId: string, file: GovernanceDownload, expectedSha256: string) {
  const route = file.sourceId ? `governance-sources/${file.origin}/${encodeURIComponent(file.reference)}/${file.sourceId}` : `governance-memo-files/${file.origin}/${encodeURIComponent(file.reference)}`
  const response = await rawFetch(path(route, enrollmentId))
  if (!response.ok) throw new ApiError(response.status, 'The preserved capstone file could not be downloaded.')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength > 3 * 1024 * 1024) throw new Error('This download exceeds the saved file limit.')
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
  if (digest !== expectedSha256) throw new Error('The downloaded bytes differ from the exact saved file. Read the original record again.')
  return new Blob([bytes], { type: response.headers.get('content-type') || 'application/octet-stream' })
}
