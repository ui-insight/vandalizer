import { describe, it, expect } from 'vitest'
import { mergeAttachedKBs, MAX_ATTACHED_KBS } from './WorkspaceContext'

const kb = (uuid: string) => ({ uuid, title: uuid.toUpperCase() })

// The first version of this decided per KB inside a React state updater and
// returned the outcome from there. React defers the updater once one is
// queued, so attaching three at once attached the first, reported a false
// "at most 3" error on the second, and dropped the third.
describe('mergeAttachedKBs', () => {
  it('attaches a whole batch in one go', () => {
    expect(mergeAttachedKBs([], [kb('a'), kb('b'), kb('c')]).map(k => k.uuid))
      .toEqual(['a', 'b', 'c'])
  })

  it('ignores a KB that is already attached', () => {
    expect(mergeAttachedKBs([kb('a')], [kb('a'), kb('b')]).map(k => k.uuid))
      .toEqual(['a', 'b'])
  })

  it('stops at the limit instead of overfilling', () => {
    const merged = mergeAttachedKBs([kb('a')], [kb('b'), kb('c'), kb('d')])
    expect(merged).toHaveLength(MAX_ATTACHED_KBS)
    expect(merged.map(k => k.uuid)).toEqual(['a', 'b', 'c'])
  })

  it('returns the same array when nothing changes, so React can skip the render', () => {
    const prev = [kb('a')]
    expect(mergeAttachedKBs(prev, [kb('a')])).toBe(prev)
    expect(mergeAttachedKBs(prev, [])).toBe(prev)
  })
})
