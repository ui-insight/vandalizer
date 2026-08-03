import { describe, it, expect, vi } from 'vitest'
import { downloadCSV, formatDate, formatDateTime, parseUtcDate } from './format'

/** downloadCSV writes to a Blob via a synthetic <a> download; to assert on the
 * generated CSV text we intercept the Blob passed to URL.createObjectURL
 * (and no-op the DOM side effects) rather than touching escape() directly,
 * since it's a private closure. */
function captureCSV(run: () => void): Promise<string> {
  let captured: Blob | null = null
  const createSpy = vi.spyOn(URL, 'createObjectURL').mockImplementation((obj: Blob | MediaSource) => {
    captured = obj as Blob
    return 'blob:mock'
  })
  const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  try {
    run()
  } finally {
    createSpy.mockRestore()
    revokeSpy.mockRestore()
    clickSpy.mockRestore()
  }
  return captured!.text()
}

describe('downloadCSV escaping', () => {
  it('prefixes a value starting with = with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['=SUM(A1:A9)']]))
    expect(csv).toBe('Col\n\'=SUM(A1:A9)')
  })

  it('prefixes a value starting with + with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['+1234']]))
    expect(csv).toBe('Col\n\'+1234')
  })

  it('prefixes a value starting with - with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['-1234']]))
    expect(csv).toBe('Col\n\'-1234')
  })

  it('prefixes a value starting with @ with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['@cmd']]))
    expect(csv).toBe('Col\n\'@cmd')
  })

  it('prefixes a value starting with a tab with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['\tpayload']]))
    expect(csv).toBe('Col\n\'\tpayload')
  })

  it('prefixes a value starting with a CR with an apostrophe', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['\rpayload']]))
    expect(csv).toBe('Col\n\'\rpayload')
  })

  it('still quotes a value containing a comma', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['Smith, Jane']]))
    expect(csv).toBe('Col\n"Smith, Jane"')
  })

  it('still escapes a value containing a double quote', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['She said "hi"']]))
    expect(csv).toBe('Col\n"She said ""hi"""')
  })

  it('leaves a plain value unchanged', async () => {
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['Hello']]))
    expect(csv).toBe('Col\nHello')
  })

  it('prefixes a lone hyphen placeholder (starts with -) with an apostrophe', async () => {
    // Several tabs pass a literal '-' as a placeholder for missing data. It
    // starts with '-', so the injection guard applies to it the same as any
    // other value — asserting this explicitly so the tradeoff is intentional,
    // not an accident of the regex.
    const csv = await captureCSV(() => downloadCSV('f.csv', ['Col'], [['-']]))
    expect(csv).toBe("Col\n'-")
  })
})

describe('parseUtcDate', () => {
  it('treats a suffix-less timestamp as UTC', () => {
    const d = parseUtcDate('2026-07-24T10:00:00')
    expect(d.toISOString()).toBe('2026-07-24T10:00:00.000Z')
  })

  it('leaves a Z-suffixed timestamp unchanged', () => {
    const d = parseUtcDate('2026-07-24T10:00:00Z')
    expect(d.toISOString()).toBe('2026-07-24T10:00:00.000Z')
  })

  it('respects a positive offset', () => {
    const d = parseUtcDate('2026-07-24T10:00:00+05:00')
    expect(d.toISOString()).toBe('2026-07-24T05:00:00.000Z')
  })

  it('respects a negative offset and returns a valid Date, not Invalid Date (regression)', () => {
    const d = parseUtcDate('2026-07-24T10:00:00-07:00')
    expect(Number.isNaN(d.getTime())).toBe(false)
    expect(d.toISOString()).toBe('2026-07-24T17:00:00.000Z')
  })
})

describe('formatDate / formatDateTime', () => {
  it('formatDate returns the em-dash placeholder for null', () => {
    expect(formatDate(null)).toBe('—')
  })

  it('formatDate returns the em-dash placeholder for an unparseable string', () => {
    expect(formatDate('not-a-real-date')).toBe('—')
  })

  it('formatDateTime returns the em-dash placeholder for null', () => {
    expect(formatDateTime(null)).toBe('—')
  })

  it('formatDateTime returns the em-dash placeholder for an unparseable string', () => {
    expect(formatDateTime('not-a-real-date')).toBe('—')
  })

  it('formatDateTime output contains the 4-digit year', () => {
    const out = formatDateTime('2026-07-24T10:00:00Z')
    expect(out).toMatch(/2026/)
  })
})
