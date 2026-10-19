import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'
import type { CrawlPreview, CrawlPreviewPage } from '../../api/knowledge'

vi.mock('../../api/knowledge', () => ({
  startCrawlPreview: vi.fn(),
  getCrawlPreview: vi.fn(),
  addCrawlPreviewSelection: vi.fn(),
}))
import { addCrawlPreviewSelection, startCrawlPreview } from '../../api/knowledge'

// A double-clicked Add button used to fire two POSTs, enqueueing two ingest
// runs that raced each other and ingested the same URL twice (duplicate-
// source support ticket). Submit must latch after the first click.
describe('AddUrlsModal', () => {
  it('fires onSubmit only once for a rapid double-click', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onCrawlAdded={vi.fn()} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
      target: { value: 'https://example.com/a\nhttps://example.com/b' },
    })
    const button = screen.getByRole('button', { name: 'Add URLs' })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith(
      ['https://example.com/a', 'https://example.com/b'],
      false,
      5,
      '',
    )
  })

  it('disables the button and shows progress after submitting', () => {
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onCrawlAdded={vi.fn()} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
      target: { value: 'https://example.com/a' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))

    const button = screen.getByRole('button', { name: 'Adding…' })
    expect(button).toBeDisabled()
  })

  it('does not submit with no URLs entered', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onCrawlAdded={vi.fn()} onClose={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add URLs' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

const START = 'https://www.uidaho.edu/research/osp'
const page = (path: string, kind: CrawlPreviewPage['kind'], extra: Partial<CrawlPreviewPage> = {}): CrawlPreviewPage => ({
  url: `${START}${path}`, start_url: START, kind, title: path || 'OSP', chars: 4200, note: null, in_kb: false, ...extra,
})
const finished: CrawlPreview = {
  uuid: 'pv-1', status: 'complete', error_message: null, start_urls: [START],
  max_crawl_pages: 5, fetched: 5,
  pages: [
    page('', 'start'),
    page('/fa-rates', 'content'),
    page('/news', 'navigation', { note: 'Mostly links' }),
    page('/broken', 'failed', { note: 'HTTP 404' }),
    page('/already', 'content', { in_kb: true }),
  ],
}

// Crawling used to embed whatever it found. Now it lists the pages first and
// adds only the ticked ones (crawl dry-run support ticket).
describe('AddUrlsModal crawl preview', () => {
  beforeEach(() => {
    vi.mocked(startCrawlPreview).mockResolvedValue(finished)
    vi.mocked(addCrawlPreviewSelection).mockResolvedValue({ ok: true, added: 1 })
  })

  const openPreview = async (onSubmit = vi.fn(), onCrawlAdded = vi.fn()) => {
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onCrawlAdded={onCrawlAdded} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), { target: { value: START } })
    fireEvent.click(screen.getByLabelText('Enable crawling'))
    fireEvent.click(screen.getByRole('button', { name: 'Find pages' }))
    await screen.findByText('Choose pages to add')
    return { onSubmit, onCrawlAdded }
  }

  it('finds pages instead of adding them', async () => {
    const { onSubmit } = await openPreview()
    expect(startCrawlPreview).toHaveBeenCalledWith('kb-1', [START], 5, '')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('ticks what a crawl would add, and leaves navigation, failures and existing pages unticked', async () => {
    await openPreview()
    expect(screen.getByLabelText('Add OSP')).toBeChecked()
    expect(screen.getByLabelText('Add /fa-rates')).toBeChecked()
    expect(screen.getByLabelText('Add /news')).not.toBeChecked()
    expect(screen.getByLabelText('Add /broken')).toBeDisabled()
    expect(screen.getByLabelText('Add /already')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Add 2 pages' })).toBeEnabled()
  })

  it('adds only the pages left ticked', async () => {
    const { onCrawlAdded } = await openPreview()
    fireEvent.click(screen.getByLabelText('Add OSP'))
    fireEvent.click(screen.getByLabelText('Add /news'))
    fireEvent.click(screen.getByRole('button', { name: 'Add 2 pages' }))

    await waitFor(() => expect(onCrawlAdded).toHaveBeenCalledWith(1))
    const sent = vi.mocked(addCrawlPreviewSelection).mock.calls[0]
    expect(sent[0]).toBe('kb-1')
    expect(sent[1]).toBe('pv-1')
    expect([...sent[2]].sort()).toEqual([`${START}/fa-rates`, `${START}/news`])
  })

  it('cannot add while the crawl is still finding pages', async () => {
    vi.mocked(startCrawlPreview).mockResolvedValue({ ...finished, status: 'running' })
    await openPreview()
    expect(await screen.findByRole('button', { name: 'Add 2 pages' })).toBeDisabled()
    expect(screen.getByText(/Finding pages…/)).toBeTruthy()
  })
})
