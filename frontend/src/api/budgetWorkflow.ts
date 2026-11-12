import { apiFetch } from './client'
import type { BudgetList, BudgetCalculation, BudgetCapture, BudgetRun, BudgetReview, BudgetScope, BudgetRequest, BudgetSaved } from '../types/budgetWorkflow'
const path = (route: string, enrollmentId: string) => `/api/certification/${route}?enrollment_id=${encodeURIComponent(enrollmentId)}`
export const getBudgetWork = (enrollmentId: string) => apiFetch<BudgetList>(path('modules/advanced_nodes/budget-workflows', enrollmentId))
export const getBudgetCalculation = (enrollmentId: string, id: string) => apiFetch<BudgetCalculation>(path(`budget-calculations/${encodeURIComponent(id)}`, enrollmentId))
export const getBudgetCapture = (enrollmentId: string, id: string) => apiFetch<BudgetCapture>(path(`budget-captures/${encodeURIComponent(id)}`, enrollmentId))
export const getBudgetRun = (enrollmentId: string, id: string) => apiFetch<BudgetRun>(path(`budget-runs/${encodeURIComponent(id)}`, enrollmentId))
export const getBudgetReview = (enrollmentId: string, id: string) => apiFetch<BudgetReview>(path(`budget-reviews/${encodeURIComponent(id)}`, enrollmentId))
export const getBudgetScope = (enrollmentId: string, id: string) => apiFetch<BudgetScope>(path(`budget-scope-decisions/${encodeURIComponent(id)}`, enrollmentId))
export function saveBudgetWork(enrollmentId: string, request: BudgetRequest) {
  const routes = { calculation: 'modules/advanced_nodes/budget-calculations', capture: 'modules/advanced_nodes/budget-captures',
    prepare: 'modules/advanced_nodes/budget-runs', scope: 'budget-runs/scope', execute: 'budget-runs/execute',
    finalize: 'budget-runs/finalize', review: 'modules/advanced_nodes/budget-reviews' }
  return apiFetch<BudgetSaved>(path(routes[request.action], enrollmentId), { method: 'POST', body: JSON.stringify(request.body) })
}
