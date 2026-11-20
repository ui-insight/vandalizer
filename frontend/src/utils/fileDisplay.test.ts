import { describe, it, expect } from 'vitest'
import { fileKind, formatContentsSummary, formatFileSize, formatItemCount } from './fileDisplay'

describe('formatFileSize', () => {
  it('scales to the largest sensible unit', () => {
    expect(formatFileSize(0)).toBe('0 B')
    expect(formatFileSize(812)).toBe('812 B')
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(4.2 * 1024 * 1024)).toBe('4.2 MB')
    expect(formatFileSize(12 * 1024 * 1024)).toBe('12 MB')
    expect(formatFileSize(9.96 * 1024)).toBe('10 KB')
  })

  it('says nothing when the size is unknown', () => {
    expect(formatFileSize(null)).toBe('')
    expect(formatFileSize(undefined)).toBe('')
  })
})

describe('formatItemCount', () => {
  it('names an empty folder and pluralises', () => {
    expect(formatItemCount(0)).toBe('Empty')
    expect(formatItemCount(1)).toBe('1 item')
    expect(formatItemCount(12)).toBe('12 items')
    expect(formatItemCount(undefined)).toBe('')
  })
})

describe('formatContentsSummary', () => {
  it('counts folders and files, dropping whichever is zero', () => {
    expect(formatContentsSummary(6, 10)).toBe('6 folders, 10 documents')
    expect(formatContentsSummary(1, 0)).toBe('1 folder')
    expect(formatContentsSummary(0, 1)).toBe('1 document')
    expect(formatContentsSummary(0, 0)).toBe('Empty')
  })
})

describe('fileKind', () => {
  it('tells spreadsheets, documents and PDFs apart', () => {
    expect(fileKind('xlsx')).toBe('spreadsheet')
    expect(fileKind('.CSV')).toBe('spreadsheet')
    expect(fileKind('docx')).toBe('document')
    expect(fileKind('pdf')).toBe('pdf')
    expect(fileKind('zip')).toBe('other')
    expect(fileKind(null)).toBe('other')
  })
})
