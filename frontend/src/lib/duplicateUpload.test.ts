import { describe, expect, it } from 'vitest'
import { isUnappliedUpload, unappliedUploadMessage } from './duplicateUpload'

describe('isUnappliedUpload', () => {
  it('is false for a new file and for an identical one', () => {
    expect(isUnappliedUpload({})).toBe(false)
    expect(isUnappliedUpload({ exists: true, changed: false })).toBe(false)
  })
  it('is true when the content differs or could not be compared', () => {
    expect(isUnappliedUpload({ exists: true, changed: true })).toBe(true)
    expect(isUnappliedUpload({ exists: true, changed: null })).toBe(true)
    // An older server that doesn't send `changed` at all.
    expect(isUnappliedUpload({ exists: true })).toBe(true)
  })
})

describe('unappliedUploadMessage', () => {
  it('says the existing file was kept and the new one was not uploaded', () => {
    const text = unappliedUploadMessage('budget.xlsx', { exists: true, changed: true })
    expect(text).toContain('A different file named “budget.xlsx” is already in this folder')
    expect(text).toContain('was not replaced')
    expect(text).toContain('was not uploaded')
  })
  it('gives a way forward to someone who cannot change the existing file', () => {
    // Upload new version needs edit rights on a teammate's file.
    for (const changed of [true, null]) {
      const text = unappliedUploadMessage('budget.xlsx', { exists: true, changed })
      expect(text).toContain('Upload new version on the existing file')
      expect(text).toContain('rename yours and upload it again')
    }
  })
  it('does not claim a difference it could not check', () => {
    const text = unappliedUploadMessage('budget.xlsx', { exists: true, changed: null }, 'your files')
    expect(text).not.toContain('different')
    expect(text).toContain('already in your files and was not updated')
  })
})
