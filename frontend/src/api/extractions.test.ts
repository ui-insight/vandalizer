import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  createSearchSet,
  listSearchSets,
  getSearchSet,
  updateSearchSet,
  deleteSearchSet,
  cloneSearchSet,
  addItem,
  listItems,
  updateItem,
  deleteItem,
} from './extractions'

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

describe('SearchSet CRUD', () => {
  it('createSearchSet sends POST with title and set_type', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'ss-1', title: 'NSF Template' }))
    const result = await createSearchSet({ title: 'NSF Template' })
    expect(result.uuid).toBe('ss-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/search-sets')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body)
    expect(body.title).toBe('NSF Template')
    expect(body.set_type).toBe('extraction')
  })

  it('listSearchSets sends GET', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([{ uuid: 'ss-1' }]))
    const result = await listSearchSets()
    expect(result).toHaveLength(1)
    expect(mockFetch.mock.calls[0][0]).toBe('/api/extractions/search-sets')
  })

  it('listSearchSets passes space param', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]))
    await listSearchSets('research')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/extractions/search-sets?space=research')
  })

  it('getSearchSet sends GET with uuid', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'ss-1', title: 'Test' }))
    const result = await getSearchSet('ss-1')
    expect(result.uuid).toBe('ss-1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/extractions/search-sets/ss-1')
  })

  it('updateSearchSet sends PATCH', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'ss-1', title: 'Updated' }))
    await updateSearchSet('ss-1', { title: 'Updated' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/search-sets/ss-1')
    expect(call[1].method).toBe('PATCH')
  })

  it('deleteSearchSet sends DELETE', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))
    await deleteSearchSet('ss-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/search-sets/ss-1')
    expect(call[1].method).toBe('DELETE')
  })

  it('cloneSearchSet sends POST to clone endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ uuid: 'ss-clone-1' }))
    const result = await cloneSearchSet('ss-1')
    expect(result.uuid).toBe('ss-clone-1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/extractions/search-sets/ss-1/clone')
  })
})

describe('SearchSet Items', () => {
  it('addItem sends POST with searchphrase', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'item-1', searchphrase: 'award_number' }))
    await addItem('ss-1', { searchphrase: 'award_number' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/search-sets/ss-1/items')
    expect(call[1].method).toBe('POST')
    const body = JSON.parse(call[1].body)
    expect(body.searchphrase).toBe('award_number')
    expect(body.searchtype).toBe('extraction')
  })

  it('listItems sends GET for search set uuid', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([{ id: 'item-1' }]))
    const result = await listItems('ss-1')
    expect(result).toHaveLength(1)
    expect(mockFetch.mock.calls[0][0]).toBe('/api/extractions/search-sets/ss-1/items')
  })

  it('updateItem sends PATCH', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 'item-1', searchphrase: 'pi_name' }))
    await updateItem('item-1', { searchphrase: 'pi_name' })
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/items/item-1')
    expect(call[1].method).toBe('PATCH')
  })

  it('deleteItem sends DELETE', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }))
    await deleteItem('item-1')
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('/api/extractions/items/item-1')
    expect(call[1].method).toBe('DELETE')
  })
})
