import { apiFetch } from './client'
import type { ConnectedList, ConnectedCapture, ConnectedRun, ConnectedReview, ConnectedScope, ConnectedRequest, ConnectedSaved, ConnectedRecoveryDecision } from '../types/connectedWorkflow'

const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const getConnectedWork = (enrollmentId: string) => apiFetch<ConnectedList>(path('modules/multi_step/connected-workflows', enrollmentId))
export const getConnectedCapture = (enrollmentId: string, id: string) => apiFetch<ConnectedCapture>(path(`connected-captures/${encodeURIComponent(id)}`, enrollmentId))
export const getConnectedRun = (enrollmentId: string, id: string) => apiFetch<ConnectedRun>(path(`connected-runs/${encodeURIComponent(id)}`, enrollmentId))
export const getConnectedReview = (enrollmentId: string, id: string) => apiFetch<ConnectedReview>(path(`connected-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getConnectedScope = (enrollmentId: string, id: string) => apiFetch<ConnectedScope>(path(`connected-scope-decisions/${encodeURIComponent(id)}`, enrollmentId))
export const getConnectedRecoveryDecision = (enrollmentId: string, id: string) => apiFetch<ConnectedRecoveryDecision>(path(`connected-recovery-decisions/${encodeURIComponent(id)}`, enrollmentId))
export function saveConnectedWork(enrollmentId: string, request: ConnectedRequest) {
  const routes = { capture: 'modules/multi_step/connected-captures', prepare: 'modules/multi_step/connected-runs',
    scope: 'connected-runs/scope', execute: 'connected-runs/execute', finalize: 'connected-runs/finalize', review: 'modules/multi_step/connected-reviews', recovery: 'modules/multi_step/connected-recovery-decisions' }
  return apiFetch<ConnectedSaved>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
}
