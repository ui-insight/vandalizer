import { describe, expect, it } from 'vitest'
import { filenameFromDisposition } from './contentDisposition'

describe('filenameFromDisposition', () => {
  it('prefers the UTF-8 name over the ASCII stand-in', () => {
    const header = `attachment; filename="Year-by-Year Budget nih-r01-neuroscience.xlsx"; filename*=UTF-8''Year-by-Year%20Budget%20%E2%80%94%20nih-r01-neuroscience.xlsx`
    expect(filenameFromDisposition(header, 'x')).toBe('Year-by-Year Budget — nih-r01-neuroscience.xlsx')
  })

  it('reads a plain quoted or bare name', () => {
    expect(filenameFromDisposition('attachment; filename="report.zip"', 'x')).toBe('report.zip')
    expect(filenameFromDisposition('attachment; filename=documents.zip', 'x')).toBe('documents.zip')
  })

  it('falls back when there is no usable name', () => {
    expect(filenameFromDisposition(null, 'folder.zip')).toBe('folder.zip')
    expect(filenameFromDisposition('attachment', 'folder.zip')).toBe('folder.zip')
    expect(filenameFromDisposition(`attachment; filename="a.zip"; filename*=UTF-8''%E2%80`, 'x')).toBe('a.zip')
  })
})
