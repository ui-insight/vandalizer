import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listLibraries,
  listItems,
  cloneToPersonal,
  shareToTeam,
  listCollections,
  submitForVerification,
} from './library'

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

describe('Library API', () => {
  it('listLibraries sends GET', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]))
    const result = await listLibraries()
    expect(result).toEqual([])
    expect(mockFetch.mock.calls[0][0]).toContain('/api/library')
  })

  it('listLibraries passes team_id param', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]))
    await listLibraries('team-1')
    expect(mockFetch.mock.calls[0][0]).toContain('team_id=team-1')
  })

  it('listItems sends GET with library id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([{ id: 'i1' }]))
    const result = await listItems('lib-1')
    expect(result).toHaveLength(1)
    expect(mockFetch.mock.calls[0][0]).toContain('/api/library/lib-1/items')
  })

  it('listItems passes filter params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]))
    await listItems('lib-1', { kind: 'workflow', search: 'budget' })
    const url = mockFetch.mock.calls[0][0]
    expect(url).toContain('kind=workflow')
    expect(url).toContain('search=budget')
  })

  it('cloneToPersonal sends POST with item_id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'cloned-1' }))
    await cloneToPersonal('item-1')
    const call = mockFetch.mock.calls[0]
    expect(call[1].method).toBe('POST')
    expect(call[0]).toBe('/api/library/clone')
    const body = JSON.parse(call[1].body)
    expect(body.item_id).toBe('item-1')
  })

  it('shareToTeam sends POST with item_id and team_id', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'shared-1' }))
    await shareToTeam('item-1', 'team-1')
    const call = mockFetch.mock.calls[0]
    expect(call[1].method).toBe('POST')
    expect(call[0]).toBe('/api/library/share')
    const body = JSON.parse(call[1].body)
    expect(body.item_id).toBe('item-1')
    expect(body.team_id).toBe('team-1')
  })

  it('listCollections sends GET', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ collections: [{ id: 'c1', title: 'Pre-Award' }] }),
    )
    const result = await listCollections()
    expect(result.collections).toHaveLength(1)
    expect(result.collections[0].title).toBe('Pre-Award')
  })

  it('submitForVerification sends POST with required fields', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ uuid: 'vr-1', status: 'submitted' }),
    )
    const result = await submitForVerification({
      item_kind: 'workflow',
      item_id: 'wf-1',
      summary: 'Budget analysis workflow',
    })
    expect(result.status).toBe('submitted')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/verification/submit')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body)
    expect(body.item_kind).toBe('workflow')
    expect(body.item_id).toBe('wf-1')
    expect(body.summary).toBe('Budget analysis workflow')
  })
})
