import { describe, it, expect } from 'vitest'
import {
  base64ByteLength,
  describeFileSummary,
  formatBytes,
  isFileDownloadPayload,
  isMarkdownType,
  summarizeFilePayload,
  TEXT_PREVIEW_MAX_CHARS,
} from './outputFilePayload'

// Browser-typed tsconfig: no Buffer. Encode UTF-8 bytes to a binary string for btoa.
const b64 = (s: string) => btoa(Array.from(new TextEncoder().encode(s), b => String.fromCharCode(b)).join(''))

describe('summarizeFilePayload', () => {
  // Support ticket: a run ending in a Document Renderer step showed
  // `{type, filename, data_b64: "SGVsbG8…"}` pretty-printed as the result.
  it('describes a rendered markdown document as a file with its decoded text', () => {
    const s = summarizeFilePayload({
      type: 'file_download', data_b64: b64('# Report\n\nHello'), file_type: 'md', filename: 'report.md',
    })
    expect(s).toEqual({
      filename: 'report.md', fileType: 'md', sizeBytes: 15, text: '# Report\n\nHello', textTruncated: false,
    })
  })

  it('unwraps the {output: payload} shape the status endpoint returns', () => {
    const s = summarizeFilePayload({ output: { type: 'file_download', data_b64: b64('a,b\n1,2'), file_type: 'csv', filename: 'export.csv' } })
    expect(s?.filename).toBe('export.csv')
    expect(s?.text).toBe('a,b\n1,2')
  })

  it('gives binaries a card with no inline text', () => {
    const s = summarizeFilePayload({ type: 'file_download', data_b64: 'UEsDBAo=', file_type: 'zip', filename: 'package.zip' })
    expect(s).toMatchObject({ filename: 'package.zip', fileType: 'zip', text: null })
    expect(summarizeFilePayload({ type: 'file_download', data_b64: b64('x'), file_type: 'docx', filename: 'out.docx' })?.text).toBeNull()
  })

  it('falls back to the filename extension, then "bin", for the type and name', () => {
    expect(summarizeFilePayload({ type: 'file_download', data_b64: b64('x'), filename: 'notes.TXT' })).toMatchObject({ fileType: 'txt', text: 'x' })
    expect(summarizeFilePayload({ type: 'file_download', data_b64: b64('x') })).toMatchObject({ fileType: 'bin', filename: 'output.bin', text: null })
  })

  it('is null for anything that is not a file payload', () => {
    expect(summarizeFilePayload('# plain markdown')).toBeNull()
    expect(summarizeFilePayload({ type: 'file_download' })).toBeNull() // no data
    expect(summarizeFilePayload({ output: 'text' })).toBeNull()
    expect(summarizeFilePayload(null)).toBeNull()
    expect(summarizeFilePayload(42)).toBeNull()
  })

  it('caps the inline text preview and says so', () => {
    const big = 'x'.repeat(TEXT_PREVIEW_MAX_CHARS + 10)
    const s = summarizeFilePayload({ type: 'file_download', data_b64: b64(big), file_type: 'txt', filename: 'big.txt' })
    expect(s?.text?.length).toBe(TEXT_PREVIEW_MAX_CHARS)
    expect(s?.textTruncated).toBe(true)
  })

  it('survives a payload whose base64 is not decodable', () => {
    const s = summarizeFilePayload({ type: 'file_download', data_b64: '!!!not base64!!!', file_type: 'md', filename: 'x.md' })
    expect(s?.filename).toBe('x.md')
    expect(s?.text).toBeNull()
  })
})

describe('helpers', () => {
  it('measures base64 without decoding', () => {
    expect(base64ByteLength('')).toBe(0)
    expect(base64ByteLength(b64('abc'))).toBe(3)
    expect(base64ByteLength(b64('abcd'))).toBe(4)
    expect(base64ByteLength(b64('abcde'))).toBe(5)
  })

  it('formats sizes and one-line descriptions', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
    expect(describeFileSummary({ filename: 'report.docx', fileType: 'docx', sizeBytes: 2048, text: null, textTruncated: false }))
      .toBe('report.docx (DOCX, 2.0 KB)')
  })

  it('recognises payloads and markdown types', () => {
    expect(isFileDownloadPayload({ type: 'file_download', data_b64: '' })).toBe(true)
    expect(isFileDownloadPayload({ type: 'file_download' })).toBe(false)
    expect(isMarkdownType('md')).toBe(true)
    expect(isMarkdownType('csv')).toBe(false)
  })
})
