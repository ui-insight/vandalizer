import { describe, expect, it, vi } from 'vitest'
import { isUnappliedUpload, saveGeneratedFile, unappliedUploadMessage } from './duplicateUpload'

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

// "Save to project" writes "<set>-results-<date>.csv". A second save the same
// day met the first one's name: the server kept the old CSV and the page said
// "Saved to project".
describe('saveGeneratedFile', () => {
  const at = new Date(2026, 10, 18, 14, 5, 9)
  it('saves under the plain name when it is free', async () => {
    const save = vi.fn().mockResolvedValue({ uuid: 'd1' })
    const out = await saveGeneratedFile(save, 'Awards-results-2026-11-18', 'csv', at)
    expect(out.outcome).toBe('saved')
    expect(save.mock.calls).toEqual([['Awards-results-2026-11-18.csv']])
  })
  it('saves newer results under the time when the name holds different content', async () => {
    const save = vi.fn().mockResolvedValueOnce({ exists: true, changed: true }).mockResolvedValueOnce({ uuid: 'd2' })
    const out = await saveGeneratedFile(save, 'Awards-results-2026-11-18', 'csv', at)
    expect(out).toMatchObject({ outcome: 'saved', fileName: 'Awards-results-2026-11-18-140509.csv' })
    expect(save).toHaveBeenLastCalledWith('Awards-results-2026-11-18-140509.csv')
  })
  it('does not save a second copy of identical results', async () => {
    const save = vi.fn().mockResolvedValue({ exists: true, changed: false })
    const out = await saveGeneratedFile(save, 'Awards-results-2026-11-18', 'csv', at)
    expect(out.outcome).toBe('identical')
    expect(save).toHaveBeenCalledTimes(1)
  })
  it('reports a refusal when the timed name is taken too, or the content could not be compared', async () => {
    const save = vi.fn().mockResolvedValue({ exists: true, changed: null })
    const out = await saveGeneratedFile(save, 'Awards-results-2026-11-18', 'csv', at)
    expect(out).toMatchObject({ outcome: 'refused', fileName: 'Awards-results-2026-11-18-140509.csv' })
    expect(save).toHaveBeenCalledTimes(2)
  })
})
