import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'

const api = vi.hoisted(() => ({
  getSourceSuggestionsAvailable: vi.fn(),
  suggestSources: vi.fn(),
  readSitemap: vi.fn(),
}))
vi.mock('../../api/knowledge', () => api)

// Feature request: describe a topic, approve suggested pages, instead of
// hunting down links. Suggestions go to Add URLs' review step, unchecked.
describe('Find pages by topic', () => {
  beforeEach(() => {
    api.getSourceSuggestionsAvailable.mockReset()
    api.suggestSources.mockReset()
  })

  it('is hidden where web search is not configured', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: false })
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    await waitFor(() => expect(api.getSourceSuggestionsAvailable).toHaveBeenCalledWith('kb-1'))
    expect(screen.queryByRole('tab', { name: 'Topic' })).toBeNull()
  })

  it('sends checked suggestions through Add', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: true })
    api.suggestSources.mockResolvedValue({
      available: true, queries: ['NSF proposal requirements'], already_in_kb: 2, error: null,
      suggestions: [
        { url: 'https://nsf.gov/pappg', title: 'PAPPG', snippet: '', host: 'nsf.gov', reason: 'The proposal guide.' },
        { url: 'https://nsf.gov/budget', title: 'Budget', snippet: 'Budget rules', host: 'nsf.gov', reason: null },
      ],
    })
    const onSubmit = vi.fn()
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={onSubmit} onClose={vi.fn()} />)

    fireEvent.click(await screen.findByRole('tab', { name: 'Topic' }))
    fireEvent.change(screen.getByLabelText(/Topic/, { selector: 'input' }), { target: { value: 'NSF proposal requirements' } })
    fireEvent.click(screen.getByRole('button', { name: /Find pages/ }))

    expect(await screen.findByText('The proposal guide.')).toBeTruthy()
    expect(screen.getByText('Budget rules')).toBeTruthy()
    expect(screen.getByText(/2 more pages found are already in this knowledge base/)).toBeTruthy()
    expect(api.suggestSources).toHaveBeenCalledWith('kb-1', 'NSF proposal requirements')

    fireEvent.click(screen.getByLabelText('PAPPG'))
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 URL' }))
    expect(onSubmit).toHaveBeenCalledWith(['https://nsf.gov/pappg'], false, 5, '')
  })

  it('says when every page found is already in the knowledge base', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: true })
    api.suggestSources.mockResolvedValue({ available: true, queries: [], suggestions: [], already_in_kb: 3, error: null })
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('tab', { name: 'Topic' }))
    fireEvent.change(screen.getByLabelText(/Topic/, { selector: 'input' }), { target: { value: 'IRB rules' } })
    fireEvent.click(screen.getByRole('button', { name: /Find pages/ }))
    expect(await screen.findByText(/the 3 pages found are already in this knowledge base/)).toBeTruthy()
  })

  it('shows the search error', async () => {
    api.getSourceSuggestionsAvailable.mockResolvedValue({ available: true })
    api.suggestSources.mockRejectedValue(new Error('Web search failed: HTTP 401'))
    render(<AddUrlsModal kbUuid="kb-1" onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('tab', { name: 'Topic' }))
    fireEvent.change(screen.getByLabelText(/Topic/, { selector: 'input' }), { target: { value: 'IRB rules' } })
    fireEvent.click(screen.getByRole('button', { name: /Find pages/ }))
    expect(await screen.findByText('Web search failed: HTTP 401')).toBeTruthy()
  })
})
