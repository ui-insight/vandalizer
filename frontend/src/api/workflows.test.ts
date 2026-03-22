import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  createWorkflow,
  getWorkflow,
  updateWorkflow,
  deleteWorkflow,
  addStep,
  deleteStep,
  addTask,
  deleteTask,
  runWorkflow,
} from './workflows'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  mockFetch.mockReset()
  document.cookie = 'csrf_token=; max-age=0'
})

describe('Workflow CRUD', () => {
  it('createWorkflow sends POST with name', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'wf-1', name: 'Budget Review' }))
    const result = await createWorkflow({ name: 'Budget Review' })
    expect(result.uuid).toBe('wf-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body)
    expect(body.name).toBe('Budget Review')
  })

  it('getWorkflow sends GET with id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'wf-1', name: 'Test' }))
    const result = await getWorkflow('wf-1')
    expect(result.uuid).toBe('wf-1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/workflows/wf-1')
  })

  it('updateWorkflow sends PATCH', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'wf-1', name: 'Updated' }))
    await updateWorkflow('wf-1', { name: 'Updated' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/wf-1')
    expect(call[1].method).toBe('PATCH')
  })

  it('deleteWorkflow sends DELETE', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))
    await deleteWorkflow('wf-1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/workflows/wf-1')
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })
})

describe('Workflow Steps', () => {
  it('addStep sends POST to steps endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'step-1', name: 'Analyze' }))
    await addStep('wf-1', { name: 'Analyze' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/wf-1/steps')
    expect(call[1].method).toBe('POST')
  })

  it('deleteStep sends DELETE with step id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))
    await deleteStep('step-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/steps/step-1')
    expect(call[1].method).toBe('DELETE')
  })
})

describe('Workflow Tasks', () => {
  it('addTask sends POST to tasks endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'task-1', name: 'Extraction' }))
    await addTask('step-1', { name: 'Extraction' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/steps/step-1/tasks')
    expect(call[1].method).toBe('POST')
  })

  it('deleteTask sends DELETE with task id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))
    await deleteTask('task-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/tasks/task-1')
    expect(call[1].method).toBe('DELETE')
  })
})

describe('Workflow Execution', () => {
  it('runWorkflow sends POST with document_uuids', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ session_id: 'session-1' }))
    const result = await runWorkflow('wf-1', { document_uuids: ['doc-1', 'doc-2'] })
    expect(result.session_id).toBe('session-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/workflows/wf-1/run')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body)
    expect(body.document_uuids).toEqual(['doc-1', 'doc-2'])
  })
})
