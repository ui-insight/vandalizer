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
  fieldSupportState,
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

describe('fieldSupportState — unrecognised stored states', () => {
  // `support` arrives from stored snapshots cast with `as ExtractionSourceMap`,
  // so TypeScript enforces nothing at runtime. Falling through to `undefined`
  // rendered NO badge at all — the silent over-trust this work removes.
  it('falls back to deriving when the stored state is not one we know', () => {
    const src = {
      quote: 'The award is $4,200,000.',
      verified: true,
      value_supported: false,
      support: 'some_future_state',
    } as unknown as Parameters<typeof fieldSupportState>[0]
    expect(fieldSupportState(src)).toBe('quote_unsupported')
  })

  it('still prefers a recognised stored state over deriving', () => {
    const src = {
      verified: true,
      value_supported: false,
      support: 'unassessed',
    } as unknown as Parameters<typeof fieldSupportState>[0]
    expect(fieldSupportState(src)).toBe('unassessed')
  })

  it('never promotes an unmeasured legacy sidecar to supported', () => {
    const src = { quote: 'x', verified: true } as unknown as Parameters<
      typeof fieldSupportState
    >[0]
    expect(fieldSupportState(src)).toBe('unassessed')
  })

  it('reads a missing entry as unverified, not as an absent badge', () => {
    expect(fieldSupportState(undefined)).toBe('unverified')
    expect(fieldSupportState(null)).toBe('unverified')
  })
})
