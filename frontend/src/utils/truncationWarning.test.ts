import { describe, it, expect } from 'vitest'
import {
  TRUNCATION_ADMIN_REMEDY,
  isTruncationWarning,
  withAdminRemedy,
} from './truncationWarning'

const stored =
  'Output was cut off: the model response stopped at its 8,192-token output limit before finishing. ' +
  'The result below is incomplete. To fit within the limit, ask for a tighter output format (shorter answers, ' +
  'fewer fields, no restated input), split this step into smaller steps, or run it per document instead of across the whole set.'

describe('withAdminRemedy', () => {
  it('leaves the stored warning alone for a regular user', () => {
    const out = withAdminRemedy(stored, false)
    expect(out).toBe(stored)
    expect(out).not.toContain('Admin')
    expect(out).not.toContain('Response reserve')
  })

  it('appends the System Config remedy for an admin', () => {
    const out = withAdminRemedy(stored, true)
    expect(out.startsWith(stored)).toBe(true)
    expect(out).toContain(TRUNCATION_ADMIN_REMEDY)
    expect(out).toContain('Admin → System Config → Models')
  })

  it('does not append twice', () => {
    const once = withAdminRemedy(stored, true)
    expect(withAdminRemedy(once, true)).toBe(once)
  })

  it('matches a truncation warning joined onto another step warning', () => {
    const joined = `Knowledge base query matched nothing | ${stored}`
    expect(isTruncationWarning(joined)).toBe(true)
    expect(withAdminRemedy(joined, true)).toContain(TRUNCATION_ADMIN_REMEDY)
  })

  it('ignores warnings that are not about the output cap, even for admins', () => {
    const other = 'Knowledge base query matched nothing'
    expect(isTruncationWarning(other)).toBe(false)
    expect(withAdminRemedy(other, true)).toBe(other)
  })
})
