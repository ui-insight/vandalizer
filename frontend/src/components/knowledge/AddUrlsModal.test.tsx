import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'
import type { UrlPreview, UrlPreviewPage } from '../../api/knowledge'

vi.mock('../../api/knowledge', () => ({
  previewUrlsForKB: vi.fn(),
  cancelUrlPreview: vi.fn(),
  getUrlPreview: vi.fn(),
  getUrlPreviewPageText: vi.fn(),
  commitUrlPreview: vi.fn(),
}))

import { cancelUrlPreview, commitUrlPreview, getUrlPreview, getUrlPreviewPageText, previewUrlsForKB } from '../../api/knowledge'

function page(overrides: Partial<UrlPreviewPage>): UrlPreviewPage {
  return {
    page_id: 'p', url: 'https://example.gov/p', final_url: null, title: null, parent_url: null,
    verdict: 'good', addable: true, reason: null, excerpt: 'Allowable costs.', char_count: 16,
    chunk_count: 1, truncated: false, warnings: [], ...overrides,
  }
}

const PAGES: UrlPreviewPage[] = [
  page({ page_id: 'good', title: 'Policy', url: 'https://example.gov/policy', chunk_count: 4, char_count: 3800,
    excerpt: 'Allowable costs under the award.' }),
  page({ page_id: 'low', url: 'https://example.gov/short', verdict: 'low', chunk_count: 1,
    reason: 'Navigation or near-empty page — 29 characters of content, below the 1200 minimum' }),
  page({ page_id: 'empty', url: 'https://example.gov/blank', verdict: 'empty', addable: false,
    reason: 'Blocked by the site\'s bot protection', excerpt: '' }),
  page({ page_id: 'child', title: 'Rule A', url: 'https://example.gov/rule-a', parent_url: 'https://example.gov/policy',
    chunk_count: 3 }),
]

function preview(status: UrlPreview['status'], pages = PAGES): UrlPreview {
  return { preview_uuid: 'pv-1', status, error_message: null, crawl_enabled: true, pages }
}

async function enterAndPreview() {
  fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
    target: { value: 'https://example.gov/policy\nhttps://example.gov/short' },
  })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Preview pages' })) })
}

async function poll() {
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
}

describe('AddUrlsModal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(previewUrlsForKB).mockReset().mockResolvedValue({ preview_uuid: 'pv-1', status: 'running' })
    vi.mocked(getUrlPreview).mockReset().mockResolvedValue(preview('ready'))
    vi.mocked(getUrlPreviewPageText).mockReset()
    vi.mocked(commitUrlPreview).mockReset().mockResolvedValue({ ok: true, queued: 2 })
    vi.mocked(cancelUrlPreview).mockReset().mockResolvedValue({ ok: true, canceled: true })
  })
  afterEach(() => { vi.useRealTimers() })

  it('previews before adding anything, and a double-click starts one preview', async () => {
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
      target: { value: 'https://example.gov/policy' },
    })
    const button = screen.getByRole('button', { name: 'Preview pages' })
    await act(async () => { fireEvent.click(button); fireEvent.click(button) })

    expect(previewUrlsForKB).toHaveBeenCalledTimes(1)
    expect(previewUrlsForKB).toHaveBeenCalledWith('kb-1', ['https://example.gov/policy'], false, 5, '')
    expect(commitUrlPreview).not.toHaveBeenCalled()
  })

  it('does not preview with no URLs entered', () => {
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Preview pages' })).toBeDisabled()
  })

  it('shows what each page adds: good kept, low unticked with its reason, empty not addable', async () => {
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()

    expect((screen.getByLabelText('Add Policy') as HTMLInputElement).checked).toBe(true)
    expect(screen.getByText(/4 chunks/)).toBeTruthy()
    expect((screen.getByLabelText('Add https://example.gov/short') as HTMLInputElement).checked).toBe(false)
    expect(screen.getByText(/29 characters of content/)).toBeTruthy()
    const empty = screen.getByLabelText('Add https://example.gov/blank') as HTMLInputElement
    expect(empty.disabled).toBe(true)
    expect(screen.getByText('Empty or blocked')).toBeTruthy()
    expect(screen.getByText(/found by crawling https:\/\/example.gov\/policy/)).toBeTruthy()
    // Good + crawled child kept: 4 + 3 chunks.
    expect(screen.getByText('2 pages kept · 7 chunks')).toBeTruthy()
  })

  it('cannot add while pages are still being fetched', async () => {
    vi.mocked(getUrlPreview).mockResolvedValue(preview('running', PAGES.slice(0, 1)))
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()

    expect(screen.getByText(/Fetching pages… 1 page so far/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^Add / })).toBeDisabled()
  })

  it('adds only the kept pages, once, and reports the count', async () => {
    const onCommitted = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={onCommitted} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()

    fireEvent.click(screen.getByLabelText('Add https://example.gov/short'))  // keep the thin one
    fireEvent.click(screen.getByLabelText('Add Rule A'))                     // drop the crawled one
    const add = screen.getByRole('button', { name: 'Add 2 pages' })
    await act(async () => { fireEvent.click(add); fireEvent.click(add) })

    expect(commitUrlPreview).toHaveBeenCalledTimes(1)
    expect(commitUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1', ['good', 'low'])
    expect(onCommitted).toHaveBeenCalledWith(2)
  })

  it('shows a page\'s text, and loads the rest on request', async () => {
    vi.mocked(getUrlPreviewPageText).mockResolvedValue({ page_id: 'good', text: 'The whole policy text.' })
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()

    fireEvent.click(screen.getAllByRole('button', { name: 'Show text' })[0])
    expect(screen.getByText('Allowable costs under the award.')).toBeTruthy()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Show all 3,800 characters/ })) })
    expect(getUrlPreviewPageText).toHaveBeenCalledWith('kb-1', 'pv-1', 'good')
    expect(screen.getByText('The whole policy text.')).toBeTruthy()
  })

  it('Back returns to the URLs as typed', async () => {
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect((screen.getByLabelText('URLs to add, one per line') as HTMLTextAreaElement).value)
      .toBe('https://example.gov/policy\nhttps://example.gov/short')
  })
  // Support ticket: "Fetching pages…" spun for 10+ minutes with no pages and
  // no error. A stuck preview now says so and offers Retry and Cancel.
  const stalled = (): UrlPreview => ({
    ...preview('running', []),
    stalled: true,
    stall_message: "This is taking longer than expected. The server hasn't started fetching yet.",
  })

  it('says a stuck preview is taking longer than expected, with Retry and Cancel', async () => {
    vi.mocked(getUrlPreview).mockResolvedValue(preview('running', []))
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()
    expect(screen.queryByText(/taking longer than expected/)).not.toBeInTheDocument()

    vi.mocked(getUrlPreview).mockResolvedValue(stalled())
    await poll()
    expect(screen.getByText(/taking longer than expected/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel preview' })).toBeInTheDocument()
  })

  it('Retry stops the stuck preview and starts a new one with the same URLs', async () => {
    vi.mocked(getUrlPreview).mockResolvedValue(stalled())
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()
    vi.mocked(previewUrlsForKB).mockResolvedValue({ preview_uuid: 'pv-2', status: 'running' })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })) })

    expect(cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
    expect(previewUrlsForKB).toHaveBeenCalledTimes(2)
    expect(vi.mocked(previewUrlsForKB).mock.calls[1][1]).toEqual(
      ['https://example.gov/policy', 'https://example.gov/short'],
    )
  })

  it('Cancel stops the preview and returns to the URLs as typed', async () => {
    vi.mocked(getUrlPreview).mockResolvedValue(stalled())
    render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Cancel preview' })) })

    expect(cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
    expect(screen.getByLabelText('URLs to add, one per line')).toHaveValue(
      'https://example.gov/policy\nhttps://example.gov/short',
    )
  })

  it('closing the dialog stops a preview that is still fetching', async () => {
    vi.mocked(getUrlPreview).mockResolvedValue(preview('running', []))
    const { unmount } = render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()
    unmount()
    expect(cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
  })

  it('closing after the preview finished cancels nothing', async () => {
    const { unmount } = render(<AddUrlsModal kbUuid="kb-1" onCommitted={vi.fn()} onClose={vi.fn()} />)
    await enterAndPreview()
    await poll()
    unmount()
    expect(cancelUrlPreview).not.toHaveBeenCalled()
  })
})
