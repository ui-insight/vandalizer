import { describe, expect, it } from 'vitest'
import { missingFilesMessage } from './missingFiles'

describe('missingFilesMessage', () => {
  it('names a deleted file and never shows an id', () => {
    expect(missingFilesMessage(['16-delete-test.pdf'], 1, 'deleted')).toBe(
      '“16-delete-test.pdf” was deleted, so it has been removed from this chat. Your message was not sent.',
    )
  })

  it('handles several files', () => {
    expect(missingFilesMessage(['a.pdf', 'b.pdf', 'c.pdf'], 3, 'deleted')).toBe(
      '“a.pdf”, “b.pdf” and “c.pdf” were deleted, so they have been removed from this chat. Your message was not sent.',
    )
  })

  it('does not claim deletion when access may have changed', () => {
    expect(missingFilesMessage(['a.pdf'], 1, 'unavailable')).toContain('is no longer available to you (deleted, or your access changed)')
  })

  it('still reads as a sentence when the name is unknown', () => {
    expect(missingFilesMessage([], 1, 'deleted')).toBe(
      'A file attached to this chat was deleted, so it has been removed from this chat. Your message was not sent.',
    )
  })
})
