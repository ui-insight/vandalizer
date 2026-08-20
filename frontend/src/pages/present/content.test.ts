import { describe, it, expect } from 'vitest'
import { getTrack, TRACK_ORDER, TRACKS } from './content'

describe('getTrack', () => {
  it('returns each defined audience', () => {
    for (const id of TRACK_ORDER) {
      expect(getTrack(id)).toBe(TRACKS[id])
    }
  })

  it('returns undefined for an unknown audience', () => {
    expect(getTrack('accounting')).toBeUndefined()
    expect(getTrack('')).toBeUndefined()
    expect(getTrack(undefined)).toBeUndefined()
  })

  // /docs/present/$audience is public and unauthenticated. A bare index into
  // TRACKS resolves inherited members, so these returned a truthy Function —
  // the caller's `if (!track)` redirect was skipped and the next line
  // dereferenced .id and .slides on it, blank-screening the page.
  it.each([
    'toString',
    'constructor',
    'valueOf',
    'hasOwnProperty',
    'isPrototypeOf',
    'propertyIsEnumerable',
    'toLocaleString',
    '__proto__',
    '__defineGetter__',
  ])('refuses the prototype key %s', (key) => {
    expect(getTrack(key)).toBeUndefined()
  })

  it('returns something a caller can safely dereference, or nothing at all', () => {
    // The property the consumer reaches for immediately after the guard.
    for (const probe of [...TRACK_ORDER, 'toString', 'nope', '__proto__']) {
      const track = getTrack(probe)
      if (track) {
        expect(Array.isArray(track.slides)).toBe(true)
        expect(typeof track.id).toBe('string')
      }
    }
  })
})
