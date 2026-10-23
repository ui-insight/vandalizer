import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { pollStatus, retryExtraction } from '../../api/documents'
import { DocumentViewer } from './DocumentViewer'
vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }))
vi.mock('../../api/documents', () => ({ pollStatus: vi.fn().mockResolvedValue({ complete: true, status: 'completed', raw_text: 'Recovered source text' }), retryExtraction: vi.fn() }))
vi.mock('../../api/files', () => ({ downloadFileUrl: (id: string) => `/files/${id}` }))
afterEach(() => vi.unstubAllGlobals())
describe('source loading recovery', () => {
  it('distinguishes missing files from unsupported formats and retries the intended source', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(null, { status: 404 })).mockResolvedValue(new Response(null, { headers: { 'content-type': 'text/plain' } }))
    vi.stubGlobal('fetch', fetch)
    render(<DocumentViewer docUuid="source-1" />)
    expect(await screen.findByText(/This source is no longer available/)).toBeTruthy()
    expect(screen.queryByText(/format the viewer/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry source' }))
    expect(await screen.findByText('Recovered source text')).toBeTruthy()
    expect(fetch.mock.calls.map(call => call[0])).toEqual(['/files/source-1', '/files/source-1'])
  })
  it('shows access recovery and ignores a late failure from a previous document', async () => {
    let resolve!: (value: Response) => void
    const old = new Promise<Response>(r => { resolve = r })
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(old).mockResolvedValueOnce(new Response(null, { status: 403 })))
    const { rerender } = render(<DocumentViewer docUuid="old" />)
    rerender(<DocumentViewer docUuid="current" />)
    expect(await screen.findByText(/current account/)).toBeTruthy()
    await act(async () => resolve(new Response(null, { status: 404 })))
    expect(screen.queryByText(/no longer available/)).toBeNull()
    expect(screen.getByRole('link', { name: 'Open original in new tab' }).getAttribute('href')).toBe('/files/current')
  })
})


it('does not apply an extraction retry accepted after navigating to another source', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { headers: { 'content-type': 'text/plain' } })))
  vi.mocked(pollStatus).mockResolvedValue({ complete: true, status: 'error', raw_text: '', error_message: 'Extraction failed' } as never)
  let accept!: () => void
  vi.mocked(retryExtraction).mockReturnValue(new Promise(resolve => { accept = () => resolve({ ok: true } as never) }))
  const { rerender } = render(<DocumentViewer docUuid="failed-source" />)
  const retry = await screen.findByRole('button', { name: 'Retry extraction' })
  fireEvent.click(retry); fireEvent.click(retry)
  expect(retryExtraction).toHaveBeenCalledTimes(1)
  vi.mocked(pollStatus).mockResolvedValue({ complete: true, status: 'completed', raw_text: 'Current source text' } as never)
  rerender(<DocumentViewer docUuid="current-source" />)
  expect(await screen.findByText('Current source text')).toBeTruthy()
  await act(async () => accept())
  expect(screen.getByText('Current source text')).toBeTruthy()
  expect(screen.queryByText('Retrying...')).toBeNull()
})
