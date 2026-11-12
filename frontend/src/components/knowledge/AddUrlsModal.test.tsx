import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'

const api = vi.hoisted(() => ({
  getSourceSuggestionsAvailable: vi.fn(),
  suggestSources: vi.fn(),
  readSitemap: vi.fn(),
}))
vi.mock('../../api/knowledge', () => api)

const paste = (value: string) =>
  fireEvent.change(screen.getByLabelText(/Links, or any text with links in it/), { target: { value } })

describe('AddUrlsModal', () => {
  beforeEach(() => {
    Object.values(api).forEach(fn => fn.mockReset())
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: false })
  })

  // A double-clicked Add button used to fire two POSTs, enqueueing two ingest
  // runs that raced each other and ingested the same URL twice (duplicate-
  // source support ticket). Submit must latch after the first click.
  it('fires onSubmit only once for a rapid double-click', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)
    paste('https://example.com/a\nhttps://example.com/b')
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))

    const button = screen.getByRole('button', { name: 'Add 2 URLs' })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith(['https://example.com/a', 'https://example.com/b'], false, 5, '')
    expect(screen.getByRole('button', { name: 'Adding…' })).toBeDisabled()
  })

  it('does not go on with no links entered', () => {
    render(<AddUrlsModal onSubmit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Review links' })).toBeDisabled()
    paste('no links here, just words')
    expect(screen.getByText('0 links found.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Review links' })).toBeDisabled()
  })

  // Smart paste: the links are pulled out of an email or document.
  it('picks links out of pasted text and lets the user deselect before adding', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)
    paste('Hi — the policy is at https://a.gov/policy, the FAQ at www.a.gov/faq. Thanks!')
    expect(screen.getByText('2 links found.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))

    fireEvent.click(screen.getByLabelText('https://www.a.gov/faq'))
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 URL' }))
    expect(onSubmit).toHaveBeenCalledWith(['https://a.gov/policy'], false, 5, '')
  })

  it('reads links from an uploaded file', async () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'File' }))
    const file = new File(['title,url\nPAPPG,https://nsf.gov/pappg\nGPS,https://nih.gov/gps\n'], 'links.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText(/File of links/), { target: { files: [file] } })

    expect(await screen.findByText('2 links found in links.csv.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))
    expect(screen.getByText('From links.csv.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Add 2 URLs' }))
    expect(onSubmit).toHaveBeenCalledWith(['https://nsf.gov/pappg', 'https://nih.gov/gps'], false, 5, '')
  })

  it('says when a file has no links', async () => {
    render(<AddUrlsModal onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'File' }))
    fireEvent.change(screen.getByLabelText(/File of links/), { target: { files: [new File(['nothing'], 'notes.txt')] } })
    expect(await screen.findByText('No web links found in notes.txt.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Review links' })).toBeDisabled()
  })

  it('reads a sitemap and adds only the picked pages', async () => {
    api.readSitemap.mockResolvedValue({
      sitemap_url: 'https://a.gov/sitemap.xml', sitemaps_read: 1, truncated: false, errors: [],
      pages: [
        { url: 'https://a.gov/grants', lastmod: '2026-09-01T00:00:00Z', in_kb: false },
        { url: 'https://a.gov/held', lastmod: null, in_kb: true },
        { url: 'https://a.gov/news', lastmod: null, in_kb: false },
      ],
    })
    const onSubmit = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Sitemap' }))
    fireEvent.change(screen.getByLabelText(/Sitemap or site address/), { target: { value: 'a.gov' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read sitemap' }))

    expect(await screen.findByText('From https://a.gov/sitemap.xml.')).toBeTruthy()
    expect(api.readSitemap).toHaveBeenCalledWith('kb-1', 'a.gov')
    // A sitemap offers pages to choose from: nothing starts checked.
    expect(screen.getByText(/0 of 2 selected/)).toBeTruthy()
    expect(screen.getByText('Updated 2026-09-01')).toBeTruthy()
    expect(screen.getByLabelText('https://a.gov/held')).toBeDisabled()

    fireEvent.click(screen.getByLabelText('https://a.gov/grants'))
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 URL' }))
    expect(onSubmit).toHaveBeenCalledWith(['https://a.gov/grants'], false, 5, '')
  })

  it('shows why a sitemap could not be read', async () => {
    api.readSitemap.mockRejectedValue(new Error('No sitemap was found for a.gov'))
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Sitemap' }))
    fireEvent.change(screen.getByLabelText(/Sitemap or site address/), { target: { value: 'a.gov' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read sitemap' }))
    expect(await screen.findByText('No sitemap was found for a.gov')).toBeTruthy()
  })

  it('blocks a selection over the per-add limit', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)
    paste(Array.from({ length: 30 }, (_, i) => `https://a.gov/${i}`).join('\n'))
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))
    fireEvent.click(screen.getByText('Enable crawling'))
    expect(screen.getByText(/At most 25 links can be added at once with crawling on; 30 are selected/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add 30 URLs' })).toBeDisabled()
  })

  it('filters a long list and selects only what is shown', () => {
    render(<AddUrlsModal onSubmit={vi.fn()} onClose={vi.fn()} />)
    paste([...Array.from({ length: 12 }, (_, i) => `https://a.gov/news/${i}`), 'https://a.gov/grants/1'].join('\n'))
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    fireEvent.change(screen.getByLabelText('Filter links'), { target: { value: 'grants' } })
    fireEvent.click(screen.getByRole('button', { name: 'Select 1 shown' }))
    expect(screen.getByRole('button', { name: 'Add 1 URL' })).toBeEnabled()
  })

  it('keeps the pasted text on Back', async () => {
    render(<AddUrlsModal onSubmit={vi.fn()} onClose={vi.fn()} />)
    paste('https://a.gov/x')
    fireEvent.click(screen.getByRole('button', { name: 'Review links' }))
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    await waitFor(() => expect((screen.getByLabelText(/Links, or any text/) as HTMLTextAreaElement).value).toBe('https://a.gov/x'))
  })
})
