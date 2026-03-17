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

describe('approvals API', () => {
  it('listApprovals without status filter calls /api/approvals/', async () => {
    const approvals = [{ uuid: 'a1', status: 'pending', step_name: 'Review Step' }]
    mockFetch.mockResolvedValueOnce(jsonResponse({ approvals }))

    const { listApprovals } = await import('./approvals')
    const result = await listApprovals()

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toBe('/api/approvals/')
    expect(result.approvals).toEqual(approvals)
  })

  it('listApprovals with status filter includes query param', async () => {
    const approvals = [{ uuid: 'a2', status: 'approved', step_name: 'Approved Step' }]
    mockFetch.mockResolvedValueOnce(jsonResponse({ approvals }))

    const { listApprovals } = await import('./approvals')
    const result = await listApprovals('approved')

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toBe('/api/approvals/?status=approved')
    expect(result.approvals).toEqual(approvals)
  })

  it('approveRequest sends POST with comments', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Approved' }))

    const { approveRequest } = await import('./approvals')
    const result = await approveRequest('approval-uuid', 'Looks good')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/approvals/approval-uuid/approve')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body.comments).toBe('Looks good')
    expect(result.detail).toBe('Approved')
  })

  it('rejectRequest sends POST with comments', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Rejected' }))

    const { rejectRequest } = await import('./approvals')
    const result = await rejectRequest('approval-uuid', 'Missing data')

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/approvals/approval-uuid/reject')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body as string)
    expect(body.comments).toBe('Missing data')
    expect(result.detail).toBe('Rejected')
  })

  it('getApprovalCount calls /api/approvals/count', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ count: 7 }))

    const { getApprovalCount } = await import('./approvals')
    const result = await getApprovalCount()

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toBe('/api/approvals/count')
    expect(result.count).toBe(7)
  })
})
