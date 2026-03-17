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

describe('audit API', () => {
  it('queryAuditLog sends correct query params', async () => {
    const response = {
      entries: [{ uuid: 'log1', action: 'document.upload', actor_user_id: 'user1' }],
      total: 1,
      skip: 0,
      limit: 50,
    }
    mockFetch.mockResolvedValueOnce(jsonResponse(response))

    const { queryAuditLog } = await import('./audit')
    const result = await queryAuditLog({
      action: 'document.upload',
      actor_user_id: 'user1',
      skip: 0,
      limit: 50,
    })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain('/api/audit/')
    expect(calledUrl).toContain('action=document.upload')
    expect(calledUrl).toContain('actor_user_id=user1')
    expect(calledUrl).toContain('skip=0')
    expect(calledUrl).toContain('limit=50')
    expect(result.entries).toHaveLength(1)
    expect(result.total).toBe(1)
  })

  it('exportAuditLog returns correct URL string', async () => {
    const { exportAuditLog } = await import('./audit')

    const url = exportAuditLog({
      action: 'document.delete',
      resource_type: 'document',
      start_time: '2025-01-01',
      end_time: '2025-12-31',
    })

    expect(url).toContain('/api/audit/export')
    expect(url).toContain('action=document.delete')
    expect(url).toContain('resource_type=document')
    expect(url).toContain('start_time=2025-01-01')
    expect(url).toContain('end_time=2025-12-31')
  })

  it('exportAuditLog with no params returns base URL', async () => {
    const { exportAuditLog } = await import('./audit')
    const url = exportAuditLog()

    expect(url).toContain('/api/audit/export')
  })
})
