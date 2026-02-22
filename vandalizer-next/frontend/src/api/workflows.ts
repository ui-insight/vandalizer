import { apiFetch } from './client'
import type { Workflow, WorkflowStatus } from '../types/workflow'

// Workflow CRUD

export function createWorkflow(data: { name: string; space?: string; description?: string }) {
  return apiFetch<Workflow>('/api/workflows', { method: 'POST', body: JSON.stringify(data) })
}

export function listWorkflows(space?: string) {
  const params = space ? `?space=${encodeURIComponent(space)}` : ''
  return apiFetch<Workflow[]>(`/api/workflows${params}`)
}

export function getWorkflow(id: string) {
  return apiFetch<Workflow>(`/api/workflows/${id}`)
}

export function updateWorkflow(id: string, data: { name?: string; description?: string }) {
  return apiFetch<Workflow>(`/api/workflows/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteWorkflow(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/${id}`, { method: 'DELETE' })
}

export function duplicateWorkflow(id: string) {
  return apiFetch<Workflow>(`/api/workflows/${id}/duplicate`, { method: 'POST' })
}

// Steps

export function addStep(workflowId: string, data: { name: string; data?: Record<string, unknown>; is_output?: boolean }) {
  return apiFetch(`/api/workflows/${workflowId}/steps`, { method: 'POST', body: JSON.stringify(data) })
}

export function updateStep(stepId: string, data: { name?: string; data?: Record<string, unknown>; is_output?: boolean }) {
  return apiFetch(`/api/workflows/steps/${stepId}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteStep(stepId: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/steps/${stepId}`, { method: 'DELETE' })
}

// Tasks

export function addTask(stepId: string, data: { name: string; data?: Record<string, unknown> }) {
  return apiFetch(`/api/workflows/steps/${stepId}/tasks`, { method: 'POST', body: JSON.stringify(data) })
}

export function updateTask(taskId: string, data: { name?: string; data?: Record<string, unknown> }) {
  return apiFetch<{ id: string; name: string; data: Record<string, unknown> }>(`/api/workflows/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteTask(taskId: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/tasks/${taskId}`, { method: 'DELETE' })
}

// Execution

export function runWorkflow(workflowId: string, data: { document_uuids: string[]; model?: string }) {
  return apiFetch<{ session_id: string }>(`/api/workflows/${workflowId}/run`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getWorkflowStatus(sessionId: string) {
  return apiFetch<WorkflowStatus>(`/api/workflows/status?session_id=${encodeURIComponent(sessionId)}`)
}

export function streamWorkflowStatus(
  sessionId: string,
  onStatus: (status: WorkflowStatus) => void,
  onError?: (err: unknown) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  const url = `/api/workflows/status/stream?session_id=${encodeURIComponent(sessionId)}`

  ;(async () => {
    try {
      const res = await fetch(url, {
        credentials: 'include',
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        onError?.(new Error('Failed to connect to workflow status stream'))
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!aborted) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error === 'not_found') {
              onError?.(new Error('Workflow result not found'))
              return
            }
            onStatus(data as WorkflowStatus)
            if (data.status === 'completed' || data.status === 'error' || data.status === 'failed') {
              return
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      if (!aborted) onError?.(err)
    }
  })()

  // Return cleanup function
  return () => {
    aborted = true
    controller.abort()
  }
}

export function testStep(data: { task_name: string; task_data: Record<string, unknown>; document_uuids: string[]; model?: string }) {
  return apiFetch<{ task_id: string }>('/api/workflows/steps/test', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getTestStepStatus(taskId: string) {
  return apiFetch<{ status: string; result?: unknown }>(`/api/workflows/steps/test/${taskId}`)
}

export function downloadResults(sessionId: string, format: string = 'json') {
  return `/api/workflows/download?session_id=${encodeURIComponent(sessionId)}&format=${format}`
}

// Step reordering

export function reorderSteps(workflowId: string, stepIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/${workflowId}/reorder-steps`, {
    method: 'POST',
    body: JSON.stringify({ step_ids: stepIds }),
  })
}

// Validation

export interface ValidationCheck {
  name: string
  status: 'PASS' | 'FAIL' | 'WARN' | 'SKIP'
  detail: string | null
}

export interface ValidationResult {
  grade: string
  summary: string
  checks: ValidationCheck[]
}

export function validateWorkflow(workflowId: string, evalPlan?: string, textInput?: string) {
  return apiFetch<ValidationResult>(`/api/workflows/${workflowId}/validate`, {
    method: 'POST',
    body: JSON.stringify({ eval_plan: evalPlan, text_input: textInput }),
  })
}
