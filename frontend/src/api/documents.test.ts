import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  mockFetch.mockReset()
  document.cookie = 'csrf_token=; max-age=0'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('documents API', () => {
  it('listContents sends space, folder, teamUuid params', async () => {
    const response = { folders: [], documents: [] }
    mockFetch.mockResolvedValueOnce(jsonResponse(response))

    const { listContents } = await import('./documents')
    const result = await listContents('research', 'folder-uuid', 'team-uuid-1')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/documents/list')
    expect(calledUrl).toContain('space=research')
    expect(calledUrl).toContain('folder=folder-uuid')
    expect(calledUrl).toContain('team_uuid=team-uuid-1')
    expect(result.folders).toEqual([])
    expect(result.documents).toEqual([])
  })

  it('listContents works with only space param', async () => {
    const response = {
      folders: [{ id: '1', title: 'Folder', uuid: 'f1', parent_id: '0', is_shared_team_root: false }],
      documents: [{ id: '2', title: 'Doc', uuid: 'd1', extension: 'pdf' }],
    }
    mockFetch.mockResolvedValueOnce(jsonResponse(response))

    const { listContents } = await import('./documents')
    const result = await listContents('default')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('space=default')
    expect(calledUrl).not.toContain('folder=')
    expect(calledUrl).not.toContain('team_uuid=')
    expect(result.folders).toHaveLength(1)
    expect(result.documents).toHaveLength(1)
  })

  it('pollStatus calls correct URL', async () => {
    const response = {
      status: 'complete',
      status_messages: [],
      complete: true,
      raw_text: 'Extracted text',
      validation_feedback: null,
      valid: true,
      path: '/uploads/test.pdf',
    }
    mockFetch.mockResolvedValueOnce(jsonResponse(response))

    const { pollStatus } = await import('./documents')
    const result = await pollStatus('doc-uuid-123')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/documents/poll_status')
    expect(calledUrl).toContain('docid=doc-uuid-123')
    expect(result.complete).toBe(true)
    expect(result.status).toBe('complete')
  })

  it('searchDocuments sends query and limit', async () => {
    const response = { items: [{ uuid: 'd1', title: 'Test Doc', snippet: '...match...' }], total: 1 }
    mockFetch.mockResolvedValueOnce(jsonResponse(response))

    const { searchDocuments } = await import('./documents')
    const result = await searchDocuments('budget report', 10)

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/documents/search')
    expect(calledUrl).toContain('q=budget+report')
    expect(calledUrl).toContain('limit=10')
    expect(result.items).toHaveLength(1)
    expect(result.total).toBe(1)
  })
})
