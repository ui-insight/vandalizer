import { describe, expect, it } from 'vitest'
import { buildChatSetupUrl, parseIdList } from './shareLink'

describe('chat setup links', () => {
  it('round-trips knowledge bases, documents and folders', () => {
    const url = new URL(buildChatSetupUrl({
      kbUuids: ['kb-1', 'kb-2', 'kb-3'], docUuids: ['doc-1'], folderUuids: ['fld-1', 'fld-2'],
    }))
    expect(url.pathname).toBe('/')
    expect(parseIdList(url.searchParams.get('kb') ?? undefined)).toEqual(['kb-1', 'kb-2', 'kb-3'])
    expect(parseIdList(url.searchParams.get('docs') ?? undefined)).toEqual(['doc-1'])
    expect(parseIdList(url.searchParams.get('folders') ?? undefined)).toEqual(['fld-1', 'fld-2'])
  })

  it('omits empty lists, so a lone knowledge base is the old ?kb= link', () => {
    const url = new URL(buildChatSetupUrl({ kbUuids: ['kb-1'], docUuids: [], folderUuids: [] }))
    expect(url.search).toBe('?kb=kb-1')
  })

  it('parses a single id, blanks and repeats', () => {
    expect(parseIdList('kb-1')).toEqual(['kb-1'])
    expect(parseIdList(' a, ,b,a ')).toEqual(['a', 'b'])
    expect(parseIdList(undefined)).toEqual([])
  })

  it('survives values the router JSON-parsed out of a hand-edited link', () => {
    expect(parseIdList(true)).toEqual(['true'])
    expect(parseIdList(123)).toEqual(['123'])
    expect(parseIdList(['a', 'b'])).toEqual(['a', 'b'])
    expect(parseIdList({ a: 1 })).toEqual([])
    expect(parseIdList(null)).toEqual([])
  })
})
