import { describe, it, expect } from 'vitest'
import { computeReorderedIds } from './reorder'

const ids = ['a', 'b', 'c', 'd']

describe('computeReorderedIds', () => {
  it('moves an item before a later target', () => {
    expect(computeReorderedIds(ids, 'a', 'c', 'before')).toEqual(['b', 'a', 'c', 'd'])
  })

  it('moves an item after a later target', () => {
    expect(computeReorderedIds(ids, 'a', 'c', 'after')).toEqual(['b', 'c', 'a', 'd'])
  })

  it('moves an item before an earlier target', () => {
    expect(computeReorderedIds(ids, 'd', 'b', 'before')).toEqual(['a', 'd', 'b', 'c'])
  })

  it('moves an item after an earlier target', () => {
    expect(computeReorderedIds(ids, 'd', 'a', 'after')).toEqual(['a', 'd', 'b', 'c'])
  })

  it('moves to the very start and very end', () => {
    expect(computeReorderedIds(ids, 'c', 'a', 'before')).toEqual(['c', 'a', 'b', 'd'])
    expect(computeReorderedIds(ids, 'b', 'd', 'after')).toEqual(['a', 'c', 'd', 'b'])
  })

  it('returns null when dropped on itself', () => {
    expect(computeReorderedIds(ids, 'b', 'b', 'before')).toBeNull()
  })

  it('returns null for no-op drops on adjacent neighbors', () => {
    // "before the next item" and "after the previous item" leave order unchanged
    expect(computeReorderedIds(ids, 'b', 'c', 'before')).toBeNull()
    expect(computeReorderedIds(ids, 'b', 'a', 'after')).toBeNull()
  })

  it('returns null for unknown drag or target ids', () => {
    expect(computeReorderedIds(ids, 'x', 'b', 'before')).toBeNull()
    expect(computeReorderedIds(ids, 'b', 'x', 'before')).toBeNull()
  })

  it('does not mutate the input array', () => {
    const input = ['a', 'b', 'c']
    computeReorderedIds(input, 'c', 'a', 'before')
    expect(input).toEqual(['a', 'b', 'c'])
  })
})
