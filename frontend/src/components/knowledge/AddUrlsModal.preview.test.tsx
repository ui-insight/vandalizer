import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'
import type { UrlPreview, UrlPreviewPage } from '../../api/knowledge'

// "Fetch & check" (#1022, carried into v5's two-step dialog): the checked links
// are fetched and shown — text, chunks, a verdict — before anything is added,
// and Add then indexes exactly what was shown.

const api = vi.hoisted(() => ({
  getSourceSuggestionsAvailable: vi.fn(),
  suggestSources: vi.fn(),
  readSitemap: vi.fn(),
  previewUrlsForKB: vi.fn(),
  cancelUrlPreview: vi.fn(),
  getUrlPreview: vi.fn(),
  getUrlPreviewPageText: vi.fn(),
  commitUrlPreview: vi.fn(),
}))
vi.mock('../../api/knowledge', () => api)

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

function renderModal(props: Partial<Parameters<typeof AddUrlsModal>[0]> = {}) {
  const onSubmit = vi.fn()
  const onCommitted = vi.fn()
  const onClose = vi.fn()
  const { unmount } = render(
    <AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onCommitted={onCommitted} onClose={onClose} {...props} />,
  )
  return { onSubmit, onCommitted, onClose, unmount }
}

async function reviewLinks(value = 'https://example.gov/policy\nhttps://example.gov/short') {
  fireEvent.change(screen.getByLabelText(/Links, or any text with links in it/), { target: { value } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Review links' })) })
}

async function check() {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Fetch & check' })) })
}

async function poll() {
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
}

describe('AddUrlsModal — Fetch & check', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    Object.values(api).forEach(fn => fn.mockReset())
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: false })
    api.previewUrlsForKB.mockResolvedValue({ preview_uuid: 'pv-1', status: 'running' })
    api.getUrlPreview.mockResolvedValue(preview('ready'))
    api.commitUrlPreview.mockResolvedValue({ ok: true, queued: 2 })
    api.cancelUrlPreview.mockResolvedValue({ ok: true, canceled: true })
  })
  afterEach(() => { vi.useRealTimers() })

  it('fetches the checked links before adding anything, and a double-click starts one check', async () => {
    const { onSubmit } = renderModal()
    await reviewLinks()
    const button = screen.getByRole('button', { name: 'Fetch & check' })
    await act(async () => { fireEvent.click(button); fireEvent.click(button) })

    expect(api.previewUrlsForKB).toHaveBeenCalledTimes(1)
    expect(api.previewUrlsForKB).toHaveBeenCalledWith(
      'kb-1', ['https://example.gov/policy', 'https://example.gov/short'], false, 5, '',
    )
    expect(api.commitUrlPreview).not.toHaveBeenCalled()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('is offered only where a check can be committed, and only for a handful of links', async () => {
    renderModal({ onCommitted: undefined })
    await reviewLinks()
    expect(screen.queryByRole('button', { name: 'Fetch & check' })).toBeNull()
  })

  it('is disabled above the per-check limit', async () => {
    renderModal()
    await reviewLinks(Array.from({ length: 51 }, (_, i) => `https://example.gov/p${i}`).join('\n'))
    expect(screen.getByRole('button', { name: 'Fetch & check' })).toBeDisabled()
    // The normal batched add still takes them all.
    expect(screen.getByRole('button', { name: 'Add 51 URLs' })).not.toBeDisabled()
  })

  it('shows what each page adds: good kept, low unticked with its reason, empty not addable', async () => {
    renderModal()
    await reviewLinks()
    await check()
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
    api.getUrlPreview.mockResolvedValue(preview('running', PAGES.slice(0, 1)))
    renderModal()
    await reviewLinks()
    await check()
    await poll()

    expect(screen.getByText(/Fetching pages… 1 page so far/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^Add / })).toBeDisabled()
  })

  it('adds only the kept pages from the checked text, once, and reports the count', async () => {
    const { onSubmit, onCommitted, onClose } = renderModal()
    await reviewLinks()
    await check()
    await poll()

    fireEvent.click(screen.getByLabelText('Add https://example.gov/short'))  // keep the thin one
    fireEvent.click(screen.getByLabelText('Add Rule A'))                     // drop the crawled one
    const add = screen.getByRole('button', { name: 'Add 2 pages' })
    await act(async () => { fireEvent.click(add); fireEvent.click(add) })

    expect(api.commitUrlPreview).toHaveBeenCalledTimes(1)
    expect(api.commitUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1', ['good', 'low'])
    expect(onSubmit).not.toHaveBeenCalled()
    expect(onCommitted).toHaveBeenCalledWith(2)
    expect(onClose).toHaveBeenCalled()
  })

  it('shows a page\'s text, and loads the rest on request', async () => {
    api.getUrlPreviewPageText.mockResolvedValue({ page_id: 'good', text: 'The whole policy text.' })
    renderModal()
    await reviewLinks()
    await check()
    await poll()

    fireEvent.click(screen.getAllByRole('button', { name: 'Show text' })[0])
    expect(screen.getByText('Allowable costs under the award.')).toBeTruthy()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Show all 3,800 characters/ })) })
    expect(api.getUrlPreviewPageText).toHaveBeenCalledWith('kb-1', 'pv-1', 'good')
    expect(screen.getByText('The whole policy text.')).toBeTruthy()
  })

  it('Back to links discards the check and keeps the selection', async () => {
    const { onSubmit } = renderModal()
    await reviewLinks()
    fireEvent.click(screen.getByLabelText('https://example.gov/short'))
    await check()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Back to links/ })) })

    expect(screen.queryByRole('list', { name: 'Fetched pages' })).toBeNull()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Add 1 URL' })) })
    expect(onSubmit).toHaveBeenCalledWith(['https://example.gov/policy'], false, 5, '')
  })

  // Support ticket: "Fetching pages…" spun for 10+ minutes with no pages and
  // no error. A stuck preview now says so and offers Retry and Cancel.
  const stalled = (): UrlPreview => ({
    ...preview('running', []),
    stalled: true,
    stall_message: "This is taking longer than expected. The server hasn't started fetching yet.",
  })

  it('says a stuck preview is taking longer than expected, with Retry and Cancel', async () => {
    api.getUrlPreview.mockResolvedValue(preview('running', []))
    renderModal()
    await reviewLinks()
    await check()
    await poll()
    expect(screen.queryByText(/taking longer than expected/)).toBeNull()

    api.getUrlPreview.mockResolvedValue(stalled())
    await poll()
    expect(screen.getByText(/taking longer than expected/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cancel preview' })).toBeTruthy()
  })

  // Dev outage 2026-10-20: the worker container was down for a day, and Retry
  // just queued another preview nothing would run.
  it('offers no Retry when no worker is running to pick the preview up', async () => {
    api.getUrlPreview.mockResolvedValue({
      ...stalled(),
      stall_message: "The server's background workers aren't running, so the preview can't start.",
      workers_down: true,
    })
    renderModal()
    await reviewLinks()
    await check()
    await poll()
    expect(screen.getByText(/background workers aren't running/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Cancel preview' })).toBeTruthy()
  })

  it('Retry stops the stuck preview and starts a new one with the same links', async () => {
    api.getUrlPreview.mockResolvedValue(stalled())
    renderModal()
    await reviewLinks()
    await check()
    await poll()
    api.previewUrlsForKB.mockResolvedValue({ preview_uuid: 'pv-2', status: 'running' })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })) })

    expect(api.cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
    expect(api.previewUrlsForKB).toHaveBeenCalledTimes(2)
    expect(api.previewUrlsForKB.mock.calls[1][1]).toEqual(
      ['https://example.gov/policy', 'https://example.gov/short'],
    )
  })

  it('Cancel stops the preview and returns to the selected links', async () => {
    api.getUrlPreview.mockResolvedValue(stalled())
    renderModal()
    await reviewLinks()
    await check()
    await poll()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Cancel preview' })) })

    expect(api.cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
    expect(screen.queryByRole('list', { name: 'Fetched pages' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Add 2 URLs' })).toBeTruthy()
  })

  it('closing the dialog stops a preview that is still fetching', async () => {
    api.getUrlPreview.mockResolvedValue(preview('running', []))
    const { unmount } = renderModal()
    await reviewLinks()
    await check()
    await poll()
    unmount()
    expect(api.cancelUrlPreview).toHaveBeenCalledWith('kb-1', 'pv-1')
  })

  it('closing after the preview finished cancels nothing', async () => {
    const { unmount } = renderModal()
    await reviewLinks()
    await check()
    await poll()
    unmount()
    expect(api.cancelUrlPreview).not.toHaveBeenCalled()
  })
})
